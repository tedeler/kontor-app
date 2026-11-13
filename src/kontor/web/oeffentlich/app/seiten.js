/* Kontor – Seiten außer der Kontoansicht (oberflaeche.md 6, 13, 14). */
import {
  BESTAND, STATUS_TEXT, abfrage, aktion, anmeldung, api, baumFolge, betragEl, betragLesen, betragText, datumEl,
  datumText, h, kategorien, kontoNach, kontoPfad, melde, nachName, neueId, oberflaeche, pfadVon, stamm, tid, zeitEl,
  zeitText,
} from "./kern.js";
import {
  abstimmungDialog, bestaetigen, dialog, feld, imDialog, knopf, knopfLeiste, kontextmenue, kontoDialog, menuePosition,
  zuordnungDialog,
} from "./ui.js";
import { kategorienBaum, kontoMenue, langeBeruehrung } from "./baum.js";
import { begruendungZeigen, filterText, layoutZuruecksetzen, wkFilterDialog } from "./konto.js";

const kopf = (seite, titel, ...werkzeuge) => {
  seite.append(h("div", { class: "seiten-kopf" }, h("h1", null, titel),
    werkzeuge.length ? h("div", { class: "werkzeuge" }, werkzeuge) : null));
};
const abschnitt = (titel, ...inhalt) => h("section", { class: "karte" }, h("h2", null, titel), inhalt);
const leer = (text) => h("p", { class: "leer" }, text);
const tabelle = (attrs, spalten, zeilen) => h("table", { class: "tabelle", ...(attrs || {}) },
  h("thead", null, h("tr", null, spalten.map((s) => h("th", { scope: "col" }, s)))), h("tbody", null, zeilen));

// ------------------------------------------------------------------ Finanzübersicht (6, 22.1)
const KATEGORIEN_OFFEN = "kontor.uebersicht.kategorien";
const KATEGORIE_GRUPPEN = [["aufwand", "Ausgaben", 1], ["ertrag", "Einnahmen", -1], ["eigenkapital", "Sonstige", -1]];

const speicherLesen = (schluessel) => { try { return localStorage.getItem(schluessel); } catch { return null; } };
const speicherSchreiben = (schluessel, wert) => { try { localStorage.setItem(schluessel, wert); } catch { /* ohne Speicher */ } };

// Zeilen eines Kontobaums (6): Baumreihenfolge, aria-level, geschlossene nur mit `mit`, Klick/Enter/Kontextmenü.
// `zellen(k, name)` liefert die Zellen nach der Namenszelle; `vz` kehrt nur die Anzeige um (22.1).
function kontoZeilen(konten, mit, praefix, zellen) {
  const nachId = new Map(konten.map((k) => [k.konto_id, k]));
  const sichtbar = konten.filter((k) => mit || !k.geschlossen).map((k) => ({ id: k.konto_id, name: k.name,
    eltern_id: k.eltern_id && nachId.has(k.eltern_id) && (mit || !nachId.get(k.eltern_id).geschlossen) ? k.eltern_id : null }));
  return baumFolge(sichtbar).map(({ konto, ebene }) => {
    const k = nachId.get(konto.id);
    const name = h("td", { "data-feld": "name", class: "name", stil: { "--stufe": String(ebene - 1) } }, k.name);
    const tr = h("tr", { tid: `${praefix}-${k.konto_id}`, "aria-level": String(ebene), tabindex: "0",
      class: "klickbar" + (k.geschlossen ? " geschlossen" : ""), "data-geschlossen": k.geschlossen ? "ja" : null },
    name, zellen(k));
    const oeffnen = () => oberflaeche.gehe(`/konten/${k.konto_id}`);
    const menue = (x, y) => kontoMenue(kontoNach(k.konto_id) || { id: k.konto_id, name: k.name, art: k.art,
      eltern_id: k.eltern_id }, x, y, tr, { namensZelle: () => name });
    tr.addEventListener("click", (e) => { if (!e.target.closest("input")) oeffnen(); });
    tr.addEventListener("keydown", (e) => {
      if (e.target !== tr) return;
      if (e.key === "Enter") { e.preventDefault(); oeffnen(); }
      else if ((e.key === "F10" && e.shiftKey) || e.key === "ContextMenu") {
        e.preventDefault(); const [x, y] = menuePosition(null, tr); menue(x, y);
      }
    });
    tr.addEventListener("contextmenu", (e) => { if (e.target.closest("input")) return; e.preventDefault(); menue(e.clientX, e.clientY); });
    return tr;
  });
}

// Betrag mit Rohwert in data-betrag, Anzeige mit Vorzeichen `vz` (22.1: Einnahmen und Sonstige umgekehrt).
function anzeigeBetrag(tag, roh, vz, attrs) {
  const el = betragEl(tag, roh * vz, attrs);
  el.setAttribute("data-betrag", String(roh));
  return el;
}

export async function uebersicht(seite) {
  const u = await api("GET", "/api/kontenuebersicht");
  kopf(seite, "Finanzübersicht");
  const bestand = u.konten.filter((k) => BESTAND.has(k.art));
  const geschlossene = h("input", { type: "checkbox", tid: "uebersicht-geschlossene", id: "uebersicht-geschlossene" });
  const tbody = h("tbody");
  const kategorienInhalt = h("div", { id: "uebersicht-kategorien-inhalt", class: "kategorien-inhalt" });
  const zeichnen = () => {
    const mit = geschlossene.checked;
    tbody.replaceChildren(...kontoZeilen(bestand, mit, "uebersicht-konto", (k) => [
      h("td", null, ARTEN[k.art] || k.art), betragEl("td", k.saldo_gesamt, { "data-feld": "saldo", class: "zahl" }),
      h("td", { class: "zahl" }, String(k.anzahl_buchungen))]));
    kategorienInhalt.replaceChildren(...KATEGORIE_GRUPPEN.flatMap(([art, titel, vz]) => {
      const liste = u.konten.filter((k) => k.art === art);
      if (!liste.length) return [];
      const summe = liste.reduce((a, k) => a + k.saldo, 0);
      return [h("table", { class: "tabelle kategorien-gruppe", tid: `uebersicht-gruppe-${art}` },
        h("caption", null, titel),
        h("thead", null, h("tr", null, ["Kategorie", "Saldo", "Buchungen"].map((x) => h("th", { scope: "col" }, x)))),
        h("tbody", null, kontoZeilen(liste, mit, "uebersicht-kategorie", (k) => [
          anzeigeBetrag("td", k.saldo_gesamt, vz, { "data-feld": "saldo", class: "zahl" }),
          h("td", { class: "zahl" }, String(k.anzahl_buchungen))])),
        h("tfoot", null, h("tr", null, h("th", { scope: "row" }, `Summe ${titel}`),
          anzeigeBetrag("td", summe, vz, { tid: `uebersicht-summe-${art}`, class: "zahl" }), h("td"))))];
    }));
  };
  geschlossene.addEventListener("change", zeichnen);
  zeichnen();
  // Kategorien: abgesetzter, einklappbarer Bereich (22.1), Zustand im Browser-Speicher
  const umschalten = h("button", { type: "button", class: "knopf knopf-flach", tid: "uebersicht-kategorien-umschalten",
    "aria-controls": "uebersicht-kategorien-inhalt" });
  const setzen = (offen) => {
    umschalten.setAttribute("aria-expanded", offen ? "true" : "false");
    umschalten.textContent = offen ? "Kategorien ausblenden" : "Kategorien einblenden";
    kategorienInhalt.hidden = !offen;
  };
  setzen(speicherLesen(KATEGORIEN_OFFEN) === "ja");
  umschalten.addEventListener("click", () => {
    const offen = umschalten.getAttribute("aria-expanded") !== "true";
    speicherSchreiben(KATEGORIEN_OFFEN, offen ? "ja" : "nein");
    setzen(offen);
  });
  for (const t of [tbody, kategorienInhalt]) {
    langeBeruehrung(t, (x) => x.closest("tr[tabindex]"), (tr, x, y) => tr.dispatchEvent(new MouseEvent("contextmenu",
      { bubbles: true, cancelable: true, clientX: x, clientY: y })));
  }
  seite.append(h("label", { class: "wahl" }, geschlossene, " geschlossene Konten anzeigen"),
    h("table", { class: "tabelle", tid: "uebersicht-tabelle" },
      h("thead", null, h("tr", null, ["Konto", "Art", "Saldo", "Buchungen"].map((s) => h("th", { scope: "col" }, s)))),
      tbody,
      h("tfoot", null, h("tr", null, h("th", { scope: "row", colspan: "2" }, "Summe der Bestandskonten"),
        betragEl("td", u.summe_bestand, { tid: "uebersicht-summe", class: "zahl" }), h("td")))),
    h("p", { class: "klein" }, "Saldo = Summe aller Splits je Konto einschließlich Unterkonten. Schulden sind negativ."),
    h("section", { class: "karte uebersicht-kategorien", tid: "uebersicht-kategorien" },
      h("div", { class: "seiten-kopf" }, h("h2", null, "Kategorien"), umschalten),
      kategorienInhalt,
      h("p", { class: "klein" }, "Ausgaben, Einnahmen und Sonstige über alle Buchungen; Einnahmen positiv angezeigt.")));
  // D-128: Kachel „Was kommt noch?“ (nur mit eingeschaltetem Mail-Abgleich), auch der Zugang auf dem Handy
  try {
    const e = await api("GET", "/api/erwartungen?grund=bestellung&grund=paypal&grund=rueckerstattung&grund=manuell");
    if (e.aktiv) {
      seite.append(h("a", { href: "/erwartet", class: "karte kachel-erwartet", tid: "kachel-erwartet" },
        h("strong", null, "Was kommt noch?"), " ",
        `${e.anzahl} offen`, e.ueberfaellig ? h("span", { class: "warnung" }, ` · ${e.ueberfaellig} überfällig`) : "",
        " · ", betragEl("span", e.summe_offen)));
    }
  } catch { /* ohne Kachel */ }
  return { titel: "Finanzübersicht" };
}

const ARTEN = { girokonto: "Girokonto", sparkonto: "Sparkonto", kreditkonto: "Kreditkonto", aufwand: "Ausgaben",
  ertrag: "Einnahmen" };

// ------------------------------------------------------------------ Konten (13.3)
export async function konten(seite) {
  const u = await api("GET", "/api/kontenuebersicht");
  const saldo = new Map(u.konten.map((k) => [k.konto_id, k]));
  kopf(seite, "Konten", knopf("Konto anlegen", { tid: "konto-anlegen", onclick: (e) => kontoDialog({ titel: "Konto anlegen",
    arten: ["girokonto", "sparkonto", "kreditkonto"], iban: true }, e.currentTarget) }));
  const zeilen = baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art))).map(({ konto: k, ebene }) => {
    const name = h("td", { class: "name", stil: { "--stufe": String(ebene - 1) } }, h("a", { href: `/konten/${k.id}` }, k.name));
    const tr = h("tr", { tid: `kontenbaum-konto-${k.id}`, "aria-level": String(ebene), class: k.geschlossen ? "geschlossen" : "" },
      name, h("td", null, ARTEN[k.art]), h("td", { class: "iban" }, k.iban || ""),
      betragEl("td", (saldo.get(k.id) || { saldo_gesamt: 0 }).saldo_gesamt, { class: "zahl" }),
      h("td", null, knopf("Abstimmen…", { tid: `kontenbaum-abstimmen-${k.id}`, "aria-label": `Konto ${k.name} abstimmen`,
        onclick: (e) => abstimmungDialog(k, e.currentTarget) })));
    tr.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      kontoMenue(k, e.clientX, e.clientY, tr, { namensZelle: () => name });
    });
    return tr;
  });
  langeBeruehrung(seite, (t) => t.closest("tr[data-testid]"), (tr, x, y) => tr.dispatchEvent(new MouseEvent("contextmenu",
    { bubbles: true, cancelable: true, clientX: x, clientY: y })));
  seite.append(zeilen.length ? tabelle({ tid: "kontenbaum" }, ["Konto", "Art", "IBAN", "Saldo", "Abstimmung"], zeilen)
    : h("div", { tid: "kontenbaum" }, leer("Noch keine Konten.")));
  return { titel: "Konten" };
}

// ------------------------------------------------------------------ Kategorien (13.1)
export async function kategorienSeite(seite) {
  kopf(seite, "Kategorien", knopf("Kategorie anlegen", { tid: "kategorie-anlegen", onclick: (e) => kontoDialog({
    titel: "Kategorie anlegen", arten: ["aufwand", "ertrag"] }, e.currentTarget) }));
  const ort = h("div", { class: "baum-rahmen" });
  const zeichnen = () => ort.replaceChildren(kategorienBaum({ neuZeichnen: zeichnen }));
  zeichnen();
  seite.append(h("p", { class: "klein" }, "Kategorien per Drag and Drop auf eine andere Kategorie ziehen (wird Unterkategorie) "
    + "oder auf die Gruppenüberschrift (oberste Ebene); ohne Maus über das Kontextmenü „Verschieben nach…“. "
    + "Mit Strg/Umschalt (oder Leertaste) mehrere markieren und über das Kontextmenü „Zusammenführen in…“ "
    + "ihre Buchungen in eine andere Kategorie überführen."), ort);
  return { titel: "Kategorien" };
}

// ------------------------------------------------------------------ Wiederkehrend (13.5)
const RHYTHMUS = { monatlich: "monatlich", vierteljaehrlich: "vierteljährlich", jaehrlich: "jährlich" };
const SERIENSTATUS = { aktiv: "aktiv", ausbleibend: "ausbleibend", beendet: "beendet" };

export async function wiederkehrend(seite) {
  const u = await api("GET", "/api/wiederkehrend");
  kopf(seite, "Wiederkehrende Buchungen", knopf("Jetzt prüfen", { onclick: async () => {
    try { await api("POST", "/api/wiederkehrend/pruefen", {}); melde("erfolg", "Wiederkehrende Buchungen geprüft."); await oberflaeche.neuLaden(); }
    catch (e) { melde("fehler", e.message); }
  } }));
  // Menü je Serie (D-118): Begründung zur jüngsten Buchung, Sprung ins Kontoblatt
  const serienMenue = (s, x, y, ausloeser) => {
    const letzte = s.buchung_ids[s.buchung_ids.length - 1];
    kontextmenue(x, y, [
      { tid: "km-serie-begruendung", text: "Warum wiederkehrend?", tun: () => begruendungZeigen(letzte, ausloeser) },
      { tid: "km-serie-springen", text: "Letzte Buchung im Kontoblatt zeigen",
        tun: () => oberflaeche.zurBuchung(s.konto_id, letzte) },
    ], ausloeser);
  };
  const zeile = (s) => {
    const name = s.empfaenger ? s.empfaenger.name : "";
    const mehr = knopf("…", { tid: `wk-menue-${s.schluessel}`, class: "knopf-flach", "aria-haspopup": "menu",
      "aria-label": `Aktionen für ${name}`, title: "Aktionen",
      onclick: (e) => { const [x, y] = menuePosition(null, e.currentTarget); serienMenue(s, x, y, e.currentTarget); } });
    const tr = h("tr", { tid: `serie-${s.schluessel}`, "data-status": s.status, tabindex: "0" },
      h("td", null, name), h("td", null, pfadVon(s.konto_id)),
      h("td", null, RHYTHMUS[s.rhythmus] || s.rhythmus), betragEl("td", s.betrag, { class: "zahl" }),
      betragEl("td", s.jahreskosten, { class: "zahl" }), datumEl("td", s.naechste_faelligkeit),
      h("td", null, SERIENSTATUS[s.status] || s.status), h("td", { class: "aktionen" }, mehr));
    tr.addEventListener("contextmenu", (e) => { e.preventDefault(); serienMenue(s, e.clientX, e.clientY, tr); });
    tr.addEventListener("keydown", (e) => {
      if (e.target === tr && ((e.key === "F10" && e.shiftKey) || e.key === "ContextMenu")) {
        e.preventDefault(); const [x, y] = menuePosition(null, tr); serienMenue(s, x, y, tr);
      }
    });
    return tr;
  };
  langeBeruehrung(seite, (t) => t.closest("tr[data-status]"), (tr, x, y) => tr.dispatchEvent(new MouseEvent("contextmenu",
    { bubbles: true, cancelable: true, clientX: x, clientY: y })));
  seite.append(h("p", null, "Summe der Jahreskosten: ", betragEl("strong", u.summe_jahreskosten)),
    tabelle({ tid: "wiederkehrend-tabelle" }, ["Empfänger", "Konto", "Rhythmus", "Betrag", "Jahreskosten", "Nächste Fälligkeit",
      "Status", h("span", { class: "nur-sr" }, "Aktionen")], u.serien.map(zeile)),
    ...(u.serien.length ? [] : [leer("Keine wiederkehrenden Buchungen erkannt.")]));
  return { titel: "Wiederkehrende Buchungen" };
}

// ------------------------------------------------------------------ Kredite (13.4)
const zinsText = (millionstel) => {
  const ganz = Math.trunc(millionstel / 10000);
  const rest = String(millionstel % 10000).padStart(4, "0").replace(/0+$/, "");
  return ganz + (rest ? "," + rest : "") + " %";
};

export async function kredite(seite) {
  const liste = await api("GET", "/api/kredite");
  kopf(seite, "Kredite", knopf("Kredit anlegen", { tid: "kredit-anlegen", onclick: (e) => kreditDialog(e.currentTarget) }));
  const ul = h("ul", { class: "karten-liste", tid: "kredite-liste" }, liste.map((k) => {
    const li = h("li", { tid: `kredit-${k.id}`, class: "karte klickbar", tabindex: "0", role: "link",
      "aria-label": `Kredit ${k.name} öffnen` },
    h("strong", null, k.name), h("span", null, " · Restschuld "), betragEl("span", k.restschuld),
    h("span", null, " · Rate "), betragEl("span", k.rate), h("span", null, " · Sollzins " + zinsText(k.sollzins)));
    const oeffnen = () => oberflaeche.gehe(`/kredite/${k.id}`);
    li.addEventListener("click", oeffnen);
    li.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); oeffnen(); } });
    return li;
  }));
  seite.append(...[ul, liste.length ? null : leer("Noch keine Kredite.")].filter(Boolean));
  return { titel: "Kredite" };
}

function kreditDialog(ausloeser) {
  dialog("kredit-dialog", "Kredit anlegen", (inhalt, d) => {
    const opt = (filter) => baumFolge(stamm.konten.filter(filter)).map(({ konto }) => h("option", { value: String(konto.id) }, kontoPfad(konto)));
    const name = h("input", { type: "text", maxlength: "200" });
    const konto = h("select", null, opt((k) => k.art === "kreditkonto"));
    const zahlung = h("select", null, opt((k) => BESTAND.has(k.art)));
    const zins = h("select", null, opt((k) => k.art === "aufwand"));
    const rest = h("input", { type: "text", inputmode: "decimal" });
    const stand = h("input", { type: "date" });
    const satz = h("input", { type: "text", inputmode: "decimal", placeholder: "3,45" });
    const rate = h("input", { type: "text", inputmode: "decimal" });
    const erste = h("input", { type: "date" });
    const empf = h("input", { type: "text", maxlength: "200" });
    const speichern = knopf("Anlegen", { class: "knopf knopf-haupt" });
    speichern.addEventListener("click", () => imDialog(d, speichern, async () => {
      const m = /^(\d+)(?:,(\d{1,4}))?$/.exec(satz.value.trim());
      const sollzins = m ? Number(m[1]) * 10000 + Number((m[2] || "0").padEnd(4, "0")) : null;
      const body = { name: name.value.trim(), konto_id: Number(konto.value), zahlungskonto_id: Number(zahlung.value),
        zins_konto_id: Number(zins.value), restschuld: betragLesen(rest.value), stand_datum: stand.value, sollzins,
        rate: betragLesen(rate.value), erste_faelligkeit: erste.value,
        bedingungen: empf.value.trim() ? [{ feld: "empfaenger", operator: "enthaelt", wert: empf.value.trim() }] : [] };
      await aktion(() => api("POST", "/api/kredite", body), { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Kredit angelegt." });
    }));
    inhalt.append(feld("Name", name), feld("Kreditkonto", konto), feld("Zahlungskonto", zahlung), feld("Zinskonto", zins),
      feld("Restschuld (€)", rest), feld("Stand am", stand), feld("Sollzins p. a. (%)", satz), feld("Rate (€)", rate),
      feld("Erste Fälligkeit", erste), feld("Empfänger der Rate (enthält)", empf),
      knopfLeiste(speichern, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

export async function kredit(seite, id) {
  const [k, plan] = await Promise.all([api("GET", `/api/kredite/${id}`), api("GET", `/api/kredite/${id}/plan`)]);
  kopf(seite, k.name);
  seite.append(abschnitt("Parameter", h("dl", { class: "werte" },
    h("dt", null, "Kreditkonto"), h("dd", null, pfadVon(k.konto_id)),
    h("dt", null, "Zahlungskonto"), h("dd", null, pfadVon(k.zahlungskonto_id)),
    h("dt", null, "Zinskonto"), h("dd", null, pfadVon(k.zins_konto_id)),
    h("dt", null, "Restschuld"), h("dd", null, betragEl("span", k.restschuld), " am ", datumText(k.stand_datum)),
    h("dt", null, "Sollzins"), h("dd", null, zinsText(k.sollzins), " (", k.zinsmethode, ")"),
    h("dt", null, "Rate"), h("dd", null, betragEl("span", k.rate), " ab ", datumText(k.erste_faelligkeit)))));
  // Jahresabgleich (K 10)
  const jahr = h("input", { type: "number", tid: "abgleich-jahr", min: "1900", max: "2999", step: "1" });
  const rest = h("input", { type: "text", inputmode: "decimal", tid: "abgleich-restschuld" });
  const zinsen = h("input", { type: "text", inputmode: "decimal", tid: "abgleich-zinsen" });
  const ergebnis = h("div", { class: "abgleich-ausgabe", "aria-live": "polite" });
  const koerper = () => {
    const r = betragLesen(rest.value);
    const z = betragLesen(zinsen.value);
    rest.setAttribute("aria-invalid", typeof r === "number" ? "false" : "true");
    zinsen.setAttribute("aria-invalid", typeof z === "number" ? "false" : "true");
    if (typeof r !== "number" || typeof z !== "number" || !/^\d{4}$/.test(jahr.value)) return null;
    return { jahr: Number(jahr.value), restschuld: r, zinsen: z };
  };
  const pruefen = knopf("Prüfen", { tid: "abgleich-pruefen", onclick: async () => {
    const body = koerper();
    if (!body) { melde("fehler", "Bitte Jahr, Restschuld und Zinsen laut Jahresauszug angeben."); return; }
    let a;
    try { a = await api("POST", `/api/kredite/${id}/jahresabgleich`, { ...body, trocken: true }); }
    catch (e) { ergebnis.replaceChildren(); melde("fehler", e.message); return; }
    const best = knopf("Abgleich buchen", { tid: "abgleich-bestaetigen", class: "knopf knopf-haupt", onclick: async () => {
      try {
        await aktion(() => api("POST", `/api/kredite/${id}/jahresabgleich`, body), { erfolg: `Jahresabgleich ${body.jahr} gebucht.` });
      } catch (e) { /* gemeldet */ }
    } });
    ergebnis.replaceChildren(h("div", { tid: "abgleich-ergebnis", class: "karte" },
      h("dl", { class: "werte" },
        h("dt", null, "Restschuld berechnet"), h("dd", null, betragEl("span", a.restschuld_berechnet, { tid: "abgleich-restschuld-berechnet" })),
        h("dt", null, "Zinsen berechnet"), h("dd", null, betragEl("span", a.zinsen_berechnet, { tid: "abgleich-zinsen-berechnet" })),
        h("dt", null, "Differenz Restschuld"), h("dd", null, betragEl("span", a.differenz_restschuld, { tid: "abgleich-differenz-restschuld" })),
        h("dt", null, "Differenz Zinsen"), h("dd", null, betragEl("span", a.differenz_zinsen, { tid: "abgleich-differenz-zinsen" }))),
      a.korrektur_splits.length ? h("ul", null, a.korrektur_splits.map((s, i) => h("li", { tid: `abgleich-korrektur-${i}` },
        s.konto_id ? pfadVon(s.konto_id) : "Zahlungskonto/Gegenbuchung", " ", betragEl("span", s.betrag), s.memo ? " – " + s.memo : "")))
        : h("p", null, "Keine Korrektur nötig."), best));
  } });
  seite.append(abschnitt("Jahresabgleich", h("div", { class: "formular-zeile" }, feld("Jahr", jahr),
    feld("Restschuld laut Auszug (€)", rest), feld("Zinsen laut Auszug (€)", zinsen), pruefen), ergebnis,
  k.abgleiche.length ? h("ul", null, k.abgleiche.map((a) => h("li", { tid: `abgleich-${a.jahr}` }, `${a.jahr}: Restschuld `,
    betragEl("span", a.restschuld), ", Zinsen ", betragEl("span", a.zinsen)))) : leer("Noch kein Jahresabgleich.")));
  seite.append(abschnitt("Tilgungsplan", tabelle({ tid: "tilgungsplan" }, ["Nr.", "Fälligkeit", "Rate", "Zins", "Tilgung", "Sondertilgung", "Restschuld"],
    plan.zeilen.map((z) => h("tr", { tid: `plan-zeile-${z.nr}` }, h("td", null, String(z.nr)), datumEl("td", z.faelligkeit),
      betragEl("td", z.rate, { class: "zahl" }), betragEl("td", z.zins, { class: "zahl" }), betragEl("td", z.tilgung, { class: "zahl" }),
      betragEl("td", z.sondertilgung, { class: "zahl" }), betragEl("td", z.restschuld_nachher, { class: "zahl" }))))));
  return { titel: k.name };
}

// ------------------------------------------------------------------ Berichte (13.6)
export async function berichte(seite) {
  kopf(seite, "Berichte");
  const bestand = baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art)));
  const konten = h("select", { tid: "bericht-konten", multiple: true, size: String(Math.min(6, Math.max(2, bestand.length))) },
    bestand.map(({ konto }) => h("option", { value: String(konto.id) }, kontoPfad(konto))));
  const von = h("input", { type: "date", tid: "bericht-von" });
  const bis = h("input", { type: "date", tid: "bericht-bis" });
  const intervall = h("select", { tid: "bericht-intervall" }, [["tag", "Tag"], ["woche", "Woche"], ["monat", "Monat"],
    ["jahr", "Jahr"]].map(([w, t]) => h("option", { value: w, selected: w === "monat" }, t)));
  const diagramm = h("div", { class: "diagramm-rahmen" });
  const ausgabe = h("div", { class: "bericht-ausgabe" });
  const csv = h("a", { tid: "export-csv", href: "/api/export/buchungen.csv", download: "" }, "Buchungen als CSV");
  const pdf = h("a", { tid: "export-pdf", href: "/api/export/buchungen.pdf", download: "" }, "Buchungen als PDF");
  let lauf = 0;
  async function laden() {
    const ids = [...konten.selectedOptions].map((o) => Number(o.value));
    const p = { konto_id: ids, von: von.value || null, bis: bis.value || null };
    csv.href = "/api/export/buchungen.csv" + abfrage({ konto_id: ids.length === 1 ? ids[0] : null, von: p.von, bis: p.bis });
    pdf.href = "/api/export/buchungen.pdf" + abfrage({ konto_id: ids.length === 1 ? ids[0] : null, von: p.von, bis: p.bis });
    if (!ids.length) { await diagrammZeichnen(diagramm, null); ausgabe.replaceChildren(leer("Bitte Konten wählen.")); return; }
    const n = ++lauf;
    seite.dataset.geladen = "nein";
    let b;
    try { b = await api("GET", "/api/berichte/kontostand" + abfrage({ ...p, intervall: intervall.value })); }
    catch (e) { if (n === lauf) { ausgabe.replaceChildren(h("p", { class: "fehler", role: "alert" }, e.message)); seite.dataset.geladen = "ja"; } return; }
    if (n !== lauf) return;
    const plot = await diagrammZeichnen(diagramm, b);
    if (n !== lauf) return;
    const hinweis = h("p", { class: "klein", tid: "bericht-zoom-hinweis", hidden: true });
    ausgabe.replaceChildren(hinweis, h("table", { class: "tabelle", tid: "bericht-tabelle" },
      h("thead", null, h("tr", null, h("th", { scope: "col" }, "Stichtag"), b.reihen.map((r) => h("th", { scope: "col" }, r.name)))),
      h("tbody", null, b.stichtage.map((tag, i) => h("tr", { tid: `bericht-zeile-${tag}` }, datumEl("th", tag, { scope: "row" }),
        b.reihen.map((r) => betragEl("td", r.werte[i], { class: "zahl", "data-konto-id": String(r.konto_id) })))))));
    const zeilen = ausgabe.querySelectorAll("tbody tr");
    // Zeile i umfasst die Buchungen nach dem vorigen Stichtag bis einschließlich ihres Stichtags
    aufklappbar(zeilen, (i) => ({ von: i ? tagDanach(b.stichtage[i - 1]) : b.stichtage[0], bis: b.stichtage[i] }),
      ids, { spalten: 1 + b.reihen.length, praefix: "bericht" });
    zoomFolgen(plot, zeilen, (tr, i) => b.stichtage[i], hinweis);
    seite.dataset.geladen = "ja";
  }
  for (const el of [konten, von, bis, intervall]) el.addEventListener("change", laden);
  const ea = h("div", { "aria-live": "polite" });
  const eaDiagramm = h("div", { class: "diagramm-rahmen", hidden: true });
  const eaLaden = knopf("Einnahmen und Ausgaben berechnen", { onclick: async () => {
    const ids = [...konten.selectedOptions].map((o) => Number(o.value));
    try {
      const b = await api("GET", "/api/berichte/einnahmen-ausgaben" + abfrage({ konto_id: ids, von: von.value || null,
        bis: bis.value || null, intervall: intervall.value }));
      eaDiagramm.hidden = !b.perioden.length;
      const plot = b.perioden.length ? await eaZeichnen(eaDiagramm, b) : null;
      const hinweis = h("p", { class: "klein", tid: "bericht-ea-zoom-hinweis", hidden: true });
      ea.replaceChildren(hinweis, tabelle(null, ["Zeitraum", "Einnahmen", "Ausgaben", "Saldo", "nicht kategorisiert"],
        b.perioden.map((p) => h("tr", null, h("td", null, `${datumText(p.von)} – ${datumText(p.bis)}`), betragEl("td", p.einnahmen, { class: "zahl" }),
          betragEl("td", p.ausgaben, { class: "zahl" }), betragEl("td", p.saldo, { class: "zahl" }),
          betragEl("td", p.nicht_kategorisiert, { class: "zahl" })))));
      const zeilen = ea.querySelectorAll("tbody tr");
      aufklappbar(zeilen, (i) => ({ von: b.perioden[i].von, bis: b.perioden[i].bis }), ids,
        { spalten: 5, praefix: "bericht-ea", ohneUmbuchungen: true });
      zoomFolgen(plot, zeilen, (tr, i) => b.perioden[i].von, hinweis);
    } catch (e) { melde("fehler", e.message); }
  } });
  seite.append(abschnitt("Kontostandsverlauf", h("div", { class: "formular-zeile" }, feld("Konten", konten), feld("Von", von),
    feld("Bis", bis), feld("Intervall", intervall)), diagramm, ausgabe),
  abschnitt("Einnahmen und Ausgaben", h("p", { class: "klein" }, "Ohne Umbuchungen; Konten, Zeitraum und Intervall wie oben."), eaLaden, eaDiagramm, ea),
  abschnitt("Export", h("p", null, csv, " · ", pdf)));
  await diagrammZeichnen(diagramm, null);
  ausgabe.replaceChildren(leer("Bitte Konten wählen."));
  return { titel: "Berichte" };
}

// ------------------------------------------------------------------ Diagramme mit Plotly (D-113)
// plotly.js (Basis-Paket, MIT) liegt unter /oeffentlich/vendor und wird erst auf der Berichtsseite geladen. Beträge
// bleiben ganze Cent: Plotly bekommt Cent-Werte, die Achsenbeschriftung entsteht mit betragText (Ganzzahlarithmetik).
let plotlyVersprechen = null;
function plotlyLaden() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  if (!plotlyVersprechen) {
    plotlyVersprechen = new Promise((ok, fehler) => {
      const el = document.createElement("script");
      el.src = "/oeffentlich/vendor/plotly-basic.min.js";
      el.onload = () => (window.Plotly ? ok(window.Plotly) : fehler(new Error("Plotly fehlt")));
      el.onerror = () => { plotlyVersprechen = null; fehler(new Error("Plotly nicht ladbar")); };
      document.head.append(el);
    });
  }
  return plotlyVersprechen;
}

/** Ganzzahlige, „runde“ Achsenteilung in Cent (1, 2, 5 · 10^k) mit höchstens etwa sechs Strichen. */
function centAchse(werte) {
  const min = Math.min(0, ...werte);
  const max = Math.max(0, ...werte) === min ? min + 100 : Math.max(0, ...werte);
  const striche = (st) => Math.ceil(max / st) - Math.floor(min / st);
  let schritt = 1;
  for (let basis = 1; schritt === 1 || striche(schritt) > 6; basis *= 10) {
    schritt = [1, 2, 5].map((f) => f * basis).find((st) => striche(st) <= 6) || 10 * basis;
    if (striche(schritt) <= 6) break;
  }
  const unten = Math.floor(min / schritt) * schritt;
  const oben = Math.ceil(max / schritt) * schritt;
  const vals = [];
  for (let v = unten; v <= oben; v += schritt) vals.push(v);
  return { tickvals: vals, ticktext: vals.map((v) => betragText(v)), range: [unten, oben] };
}

function farben() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n, x) => (cs.getPropertyValue(n) || "").trim() || x;
  return { text: v("--text", "#1a1d21"), text2: v("--text-2", "#4a525c"), rand: v("--rand", "#c9d0d9"),
    hg: v("--hg", "#ffffff"), erfolg: v("--erfolg", "#1e6b34"), gefahr: v("--gefahr", "#a8231d"), akzent: v("--akzent", "#1f5f8b") };
}

function plotlyLayout(f, achse, extra) {
  return {
    margin: { l: 100, r: 16, t: 36, b: 40 }, height: 320, separators: ",.", paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: f.text, family: "inherit" }, hovermode: "x unified", showlegend: true,
    // Tooltip in den Farben des Themas: ohne Angabe nimmt Plotly einen hellen Hintergrund
    hoverlabel: { bgcolor: f.hg, bordercolor: f.rand, font: { color: f.text, family: "inherit" } },
    legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom" },
    xaxis: { type: "date", gridcolor: f.rand, linecolor: f.rand, tickformat: "%d.%m.%Y", hoverformat: "%d.%m.%Y" },
    yaxis: { tickmode: "array", tickvals: achse.tickvals, ticktext: achse.ticktext, range: achse.range, gridcolor: f.rand,
      zeroline: true, zerolinecolor: f.text2, fixedrange: true },
    ...(extra || {}),
  };
}

const PLOTLY_OPTIONEN = { displaylogo: false, responsive: true, showSendToCloud: false, showEditInChartStudio: false,
  showLink: false, plotlyServerURL: "", topojsonURL: "/oeffentlich/vendor/",
  modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"] };

async function diagrammZeichnen(rahmen, b) {
  const beschr = b ? `Kontostandsverlauf ${b.reihen.map((r) => r.name).join(", ")} von ${datumText(b.von)} bis ${datumText(b.bis)}`
    : "Kontostandsverlauf (keine Konten gewählt)";
  const el = h("div", { tid: "bericht-diagramm", role: "img", "aria-label": beschr, class: "diagramm plotly-diagramm",
    "data-reihen": b ? String(b.reihen.length) : "0" });
  if (!b || !b.stichtage.length) {
    rahmen.replaceChildren(el);
    el.append(h("p", { class: "leer" }, b ? "Keine Daten im Zeitraum." : "Bitte Konten wählen."));
    return;
  }
  let Plotly = null;
  try { Plotly = await plotlyLaden(); } catch (e) { /* offline: einfaches SVG */ }
  if (!Plotly) { rahmen.replaceChildren(svgDiagramm(b)); return null; }
  rahmen.replaceChildren(el);
  const f = farben();
  const spuren = b.reihen.map((r, j) => ({
    type: "scatter", mode: b.stichtage.length > 60 ? "lines" : "lines+markers", name: r.name, x: b.stichtage, y: r.werte,
    line: { color: FARBEN[j % FARBEN.length], width: 2, shape: "hv" }, marker: { size: 5 },
    customdata: r.werte.map((v) => betragText(v)), hovertemplate: "%{fullData.name}: %{customdata}<extra></extra>",
  }));
  if (b.reihen.length > 1) {
    const summe = b.stichtage.map((_, i) => b.reihen.reduce((s, r) => s + r.werte[i], 0));
    spuren.push({ type: "scatter", mode: "lines", name: "Summe", x: b.stichtage, y: summe, line: { color: f.text2, width: 1.5, dash: "dot", shape: "hv" },
      customdata: summe.map((v) => betragText(v)), hovertemplate: "Summe: %{customdata}<extra></extra>" });
  }
  const achse = centAchse(spuren.flatMap((s) => s.y));
  await Plotly.newPlot(el, spuren, plotlyLayout(f, achse), PLOTLY_OPTIONEN);
  return el;
}

async function eaZeichnen(rahmen, b) {
  let Plotly = null;
  try { Plotly = await plotlyLaden(); } catch (e) { rahmen.replaceChildren(); return null; }
  const el = h("div", { tid: "bericht-ea-diagramm", role: "img", class: "diagramm plotly-diagramm",
    "aria-label": `Einnahmen und Ausgaben von ${datumText(b.von)} bis ${datumText(b.bis)}` });
  rahmen.replaceChildren(el);
  const f = farben();
  const x = b.perioden.map((p) => p.von);
  const text = (p) => `${datumText(p.von)} – ${datumText(p.bis)}`;
  const ausgaben = b.perioden.map((p) => -Math.abs(p.ausgaben));
  const spuren = [
    { type: "bar", name: "Einnahmen", x, y: b.perioden.map((p) => p.einnahmen), marker: { color: f.erfolg },
      customdata: b.perioden.map((p) => [betragText(p.einnahmen), text(p)]), hovertemplate: "Einnahmen %{customdata[1]}: %{customdata[0]}<extra></extra>" },
    { type: "bar", name: "Ausgaben", x, y: ausgaben, marker: { color: f.gefahr },
      customdata: b.perioden.map((p) => [betragText(-Math.abs(p.ausgaben)), text(p)]), hovertemplate: "Ausgaben %{customdata[1]}: %{customdata[0]}<extra></extra>" },
    { type: "scatter", mode: "lines+markers", name: "Saldo", x, y: b.perioden.map((p) => p.saldo), line: { color: f.akzent, width: 2 },
      customdata: b.perioden.map((p) => [betragText(p.saldo), text(p)]), hovertemplate: "Saldo %{customdata[1]}: %{customdata[0]}<extra></extra>" },
  ];
  const achse = centAchse(spuren.flatMap((s) => s.y));
  await Plotly.newPlot(el, spuren, plotlyLayout(f, achse, { barmode: "relative", hovermode: "closest" }), PLOTLY_OPTIONEN);
  return el;
}

const tagDanach = (iso) => {
  const d = new Date(`${iso}T12:00`);
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const MAX_EINZELBUCHUNGEN = 500;

/** Buchungen im Zeitraum mit Split auf einem der Konten `ids` (ohne Konten: alle), nach Datum. */
async function einzelbuchungen(ids, von, bis) {
  const anfragen = (ids.length ? ids : [null]).map((k) => api("GET", "/api/buchungen" + abfrage({ konto_id: k, von, bis,
    sortierung: "datum", pro_seite: MAX_EINZELBUCHUNGEN })));
  const listen = await Promise.all(anfragen);
  const nachId = new Map();
  for (const l of listen) for (const e of l.eintraege) nachId.set(e.id, e);
  const alle = [...nachId.values()].sort((a, b) => (a.datum < b.datum ? -1 : a.datum > b.datum ? 1 : a.id - b.id));
  return { eintraege: alle, unvollstaendig: listen.some((l) => l.gesamt > l.eintraege.length) };
}

/**
 * Macht die Zeilen einer Berichtstabelle aufklappbar: Aufgeklappt folgt eine Zeile mit den Einzelbuchungen des
 * Zeitraums `bereich(i)` und je beteiligtem Konto einem Knopf, der die Buchung im Kontoblatt zeigt (`?buchung=`).
 * Die Detailzeile entsteht erst beim Aufklappen; der Text der ersten Zelle bleibt unverändert.
 */
function aufklappbar(zeilen, bereich, ids, { spalten, praefix, ohneUmbuchungen }) {
  const gewaehlt = new Set(ids);
  zeilen.forEach((tr, i) => {
    const zelle = tr.firstElementChild;
    const k = h("button", { type: "button", class: "aufklapp-knopf", tid: `${praefix}-aufklappen-${i}`,
      "aria-expanded": "false", "aria-label": "Einzelbuchungen zeigen" });
    zelle.prepend(k);
    k.addEventListener("click", async () => {
      const offen = tr.dataset.offen !== "ja";
      tr.dataset.offen = offen ? "ja" : "nein";
      k.setAttribute("aria-expanded", String(offen));
      k.setAttribute("aria-label", offen ? "Einzelbuchungen ausblenden" : "Einzelbuchungen zeigen");
      if (!offen) { if (tr.detailZeile) tr.detailZeile.hidden = true; return; }
      if (tr.detailZeile) { tr.detailZeile.hidden = tr.hidden; return; }
      const inhalt = h("td", { colspan: String(spalten) }, h("p", { class: "klein" }, "Lade Buchungen …"));
      tr.detailZeile = h("tr", { class: "bericht-details", tid: `${praefix}-details-${i}` }, inhalt);
      tr.after(tr.detailZeile);
      const { von, bis } = bereich(i);
      try {
        const { eintraege, unvollstaendig } = await einzelbuchungen(ids, von, bis);
        const liste = ohneUmbuchungen ? eintraege.filter((e) => !e.ist_umbuchung) : eintraege;
        inhalt.replaceChildren(buchungsTabelle(liste, gewaehlt, praefix),
          unvollstaendig ? h("p", { class: "klein" }, `Nur die ersten ${MAX_EINZELBUCHUNGEN} Buchungen je Konto.`) : null);
      } catch (e) {
        inhalt.replaceChildren(h("p", { class: "fehler", role: "alert" }, e.message));
      }
    });
  });
}

function buchungsTabelle(liste, gewaehlt, praefix) {
  if (!liste.length) return h("p", { class: "leer" }, "Keine Buchungen in diesem Zeitraum.");
  // Betrag: Wirkung auf die gewählten Konten, ohne Auswahl auf alle Bestandskonten
  const zaehlt = (s) => (gewaehlt.size ? gewaehlt.has(s.konto_id) : BESTAND.has((kontoNach(s.konto_id) || {}).art));
  return tabelle({ class: "tabelle einzelbuchungen" }, ["Datum", "Empfänger", "Verwendungszweck", "Betrag", "Im Konto zeigen"],
    liste.map((e) => {
      const konten = [...new Set(e.splits.map((s) => s.konto_id))]
        .sort((a, b) => Number(gewaehlt.has(b)) - Number(gewaehlt.has(a)));
      return h("tr", { tid: `${praefix}-buchung-${e.id}`, "data-id": String(e.id) },
        datumEl("td", e.datum), h("td", null, e.empfaenger ? e.empfaenger.name : "–"), h("td", null, e.verwendungszweck || ""),
        betragEl("td", e.splits.filter(zaehlt).reduce((n, s) => n + s.betrag, 0), { class: "zahl" }),
        h("td", { class: "konto-knoepfe" }, konten.map((kid) => {
          const k = kontoNach(kid);
          const a = h("a", { class: "knopf knopf-flach klein", href: `/konten/${kid}?buchung=${e.id}`,
            tid: `${praefix}-buchung-${e.id}-konto-${kid}`, title: `Buchung im Konto ${k ? kontoPfad(k) : kid} zeigen` },
          k ? k.name : `Konto ${kid}`);
          // Wie „Gehe zur Gegenbuchung“: auch in einem schon offenen Tab des Kontos die Buchung wählen und fokussieren
          // (der Abfrageteil wirkt nur beim ersten Laden). Mit Strg/Mittelklick bleibt es ein normaler Link.
          a.addEventListener("click", (ev) => {
            if (ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) return;
            ev.preventDefault();
            oberflaeche.zurBuchung(kid, e.id);
          });
          return a;
        })));
    }));
}

/** Zeitpunkt eines Plotly-Datums („2024-03-15“ oder „2024-03-15 12:30:00.5“) oder einer Zahl (ms) in Ortszeit. */
function plotlyZeit(w) {
  if (typeof w === "number") return w;
  const t = String(w).replace(" ", "T");
  return Date.parse(t.length === 10 ? t + "T00:00" : t);
}

/**
 * Tabelle unter einem Diagramm zeigt nur die Zeilen, deren Datum im sichtbaren Bereich der x-Achse liegt (Zoom,
 * Verschieben). Doppelklick ins Diagramm (Autorange) zeigt wieder alle. `datum(tr, i)` liefert das Datum der Zeile
 * so, wie es im Diagramm als x-Wert steht.
 */
function zoomFolgen(plot, zeilen, datum, hinweis) {
  if (!plot || typeof plot.on !== "function") return;
  const anwenden = () => {
    const ax = (plot.layout && plot.layout.xaxis) || {};
    const r = !ax.autorange && Array.isArray(ax.range) ? ax.range.map(plotlyZeit) : null;
    let sichtbar = 0;
    zeilen.forEach((tr, i) => {
      const t = plotlyZeit(datum(tr, i));
      tr.hidden = !!r && (t < r[0] || t > r[1]);
      if (tr.detailZeile) tr.detailZeile.hidden = tr.hidden || tr.dataset.offen !== "ja";
      if (!tr.hidden) sichtbar += 1;
    });
    hinweis.hidden = !r;
    if (r) {
      const tag = (ms) => { const d = new Date(ms); return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`; };
      hinweis.textContent = `Tabelle zeigt den Ausschnitt ${tag(r[0])} – ${tag(r[1])} (${sichtbar} von ${zeilen.length} Zeilen). `
        + "Doppelklick ins Diagramm zeigt wieder alles.";
    }
  };
  plot.on("plotly_relayout", (ev) => { if (Object.keys(ev || {}).some((k) => k.startsWith("xaxis."))) anwenden(); });
}

const SVGNS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs, ...kinder) => {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
  for (const k of kinder) el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return el;
};
const FARBEN = ["#1f5f8b", "#c9781e", "#2e7d32", "#8e24aa", "#c62828", "#00838f"];

function svgDiagramm(b) {
  const B = 640;
  const H = 240;
  const rand = 40;
  const beschr = b ? `Kontostandsverlauf ${b.reihen.map((r) => r.name).join(", ")} von ${datumText(b.von)} bis ${datumText(b.bis)}`
    : "Kontostandsverlauf (keine Konten gewählt)";
  const el = svg("svg", { viewBox: `0 0 ${B} ${H}`, role: "img", "aria-label": beschr, class: "diagramm",
    preserveAspectRatio: "none" });
  el.dataset.testid = "bericht-diagramm";
  if (!b || !b.stichtage.length) return el;
  const werte = b.reihen.flatMap((r) => r.werte).concat([0]);
  const min = Math.min(...werte);
  const max = Math.max(...werte);
  const spanne = max - min || 1;
  const n = b.stichtage.length;
  const x = (i) => rand + (n === 1 ? 0 : (i * (B - 2 * rand)) / (n - 1));
  const y = (v) => H - rand / 2 - ((v - min) * (H - rand)) / spanne;
  el.append(svg("line", { x1: rand, x2: B - rand, y1: y(0), y2: y(0), class: "nulllinie" }));
  b.reihen.forEach((r, j) => {
    el.append(svg("polyline", { fill: "none", stroke: FARBEN[j % FARBEN.length], "stroke-width": 2,
      points: r.werte.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ") },
    svg("title", null, `${r.name}: ${betragText(r.werte[r.werte.length - 1])} am ${datumText(b.stichtage[n - 1])}`)));
  });
  return el;
}

// ------------------------------------------------------------------ Import (13.7)
export async function importSeite(seite) {
  kopf(seite, "Import");
  const format = h("select", { tid: "import-format" }, h("option", { value: "kmymoney" }, "KMyMoney (.kmy)"),
    h("option", { value: "gnucash" }, "GnuCash (.gnucash, XML oder SQLite)"),
    h("option", { value: "alfbanco" }, "ALF-BanCo (QIF-Export, eine Datei je Konto)"));
  const datei = h("input", { type: "file", tid: "import-datei" });
  // ALF-BanCo (D-123): Zielkonto wählen, die QIF-Datei enthält nur die Umsätze eines Kontos
  const konto = h("select", { tid: "import-konto" }, h("option", { value: "" }, "– Konto wählen –"),
    baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art))).map(({ konto: k }) => h("option", { value: String(k.id) },
      kontoPfad(k))));
  const kontoFeld = feld("Konto", konto);
  const hinweis = h("p", { class: "klein", tid: "import-hinweis-alfbanco" }, "In ALF-BanCo je Konto „Datei > Export > "
    + "Umsätze > QIF-Format“ wählen. Kategorien werden übernommen (gleichnamige vorhandene Kategorien wiederverwendet); "
    + "doppelte Kategorien lassen sich danach unter „Kategorien“ markieren und zusammenführen.");
  const formatZeigen = () => { kontoFeld.hidden = hinweis.hidden = format.value !== "alfbanco"; };
  format.addEventListener("change", formatZeigen);
  formatZeigen();
  const ausgabe = h("div", { "aria-live": "polite" });
  const starten = knopf("Import starten", { tid: "import-starten", class: "knopf knopf-haupt" });
  starten.addEventListener("click", async () => {
    if (!datei.files.length) { melde("fehler", "Bitte zuerst eine Datei wählen."); return; }
    const fd = new FormData();
    fd.append("datei", datei.files[0], datei.files[0].name);
    if (format.value === "alfbanco") {
      if (!konto.value) { melde("fehler", "Bitte das Konto wählen, zu dem die Datei gehört."); return; }
      fd.append("konto_id", konto.value);
    }
    starten.disabled = true;
    try {
      const e = await aktion(() => api("POST", `/api/import/${format.value}`, undefined, { formular: fd }),
        { erfolg: (r) => (r.erfolgreich ? "Import abgeschlossen." : "Import fehlgeschlagen.") });
      ausgabe.replaceChildren(importErgebnis(e));
    } catch (e) {
      ausgabe.replaceChildren(h("div", { tid: "import-ergebnis", "data-erfolgreich": "nein", class: "karte" },
        h("ul", null, h("li", { tid: "import-meldung" }, `${e.code}: ${e.message}`))));
    } finally { starten.disabled = false; }
  });
  seite.append(abschnitt("Datei importieren", feld("Format", format), kontoFeld, hinweis, feld("Datei", datei), starten,
    h("p", { class: "klein" }, "Der Import ist wie jede Änderung rückgängig zu machen (Strg+Z).")), ausgabe);
  return { titel: "Import", aktualisieren: async () => {} };      // Ergebnis bleibt stehen
}

const ZAEHLFELDER = ["konten_neu", "konten_vorhanden", "kategorien_neu", "kategorien_vorhanden", "empfaenger_neu",
  "empfaenger_vorhanden", "tags_neu", "tags_vorhanden", "buchungen_neu", "buchungen_vorhanden", "buchungen_zusammengefuehrt",
  "buchungen_zur_pruefung", "buchungen_uebersprungen", "splits_neu"];

function importErgebnis(e) {
  return h("div", { tid: "import-ergebnis", "data-erfolgreich": e.erfolgreich ? "ja" : "nein", class: "karte" },
    h("p", null, h("strong", null, e.erfolgreich ? "Import erfolgreich" : "Import fehlgeschlagen"), e.format ? ` (${e.format})` : ""),
    h("dl", { class: "werte" }, ZAEHLFELDER.flatMap((f) => [h("dt", null, f.replace(/_/g, " ")),
      h("dd", { tid: `import-zahl-${f}`, "data-anzahl": String(e[f]) }, String(e[f]))])),
    e.fehler.length || e.warnungen.length ? h("ul", { class: "meldungsliste" },
      [...e.fehler, ...e.warnungen].map((m) => h("li", { tid: "import-meldung" }, `${m.code}: ${m.meldung}`
        + (m.referenz ? ` (${m.referenz})` : "")))) : null);
}

// Betragsfilter wiederkehrender Buchungen (D-137): Vorgabe der Instanz und eigene Einstellungen je Empfänger
function wkFilterAbschnitt(wk) {
  const modus = h("select", { tid: "wk-vorgabe-modus" }, [["toleranz", "Toleranz in Prozent"], ["aus", "aus (jeder Betrag zählt)"]]
    .map(([w, t]) => h("option", { value: w }, t)));
  modus.value = wk.vorgabe.modus;
  const prozent = h("input", { type: "number", min: "0", max: "100", step: "1", tid: "wk-vorgabe-toleranz", inputmode: "numeric",
    value: String(wk.vorgabe.toleranz_prozent ?? 10) });
  const fProzent = feld("Toleranz (%)", prozent);
  const sichtbar = () => { fProzent.hidden = modus.value !== "toleranz"; };
  modus.addEventListener("change", sichtbar);
  sichtbar();
  const speichern = knopf("Speichern", { tid: "wk-vorgabe-speichern", onclick: async () => {
    const k = modus.value === "toleranz" ? { modus: "toleranz", toleranz_prozent: Number(prozent.value) } : { modus: "aus" };
    try { await api("PUT", "/api/wiederkehrend/einstellungen/vorgabe", k); melde("erfolg", "Vorgabe gespeichert."); await oberflaeche.neuLaden(); }
    catch (e) { melde("fehler", e.message); }
  } });
  const zeilen = wk.empfaenger.map((x) => h("tr", { tid: `wk-filter-${x.empfaenger.id}`, "data-modus": x.modus },
    h("td", null, x.empfaenger.name), h("td", null, filterText(x)),
    h("td", null, knopf("Ändern …", { "aria-label": `Betragsfilter für ${x.empfaenger.name} ändern`,
      onclick: (e) => wkFilterDialog(x.empfaenger, e.currentTarget) }),
    knopf("Entfernen", { tid: `wk-filter-entfernen-${x.empfaenger.id}`, "aria-label": `Betragsfilter für ${x.empfaenger.name} entfernen`,
      onclick: async () => {
        try { await aktion(() => api("DELETE", `/api/empfaenger/${x.empfaenger.id}/wiederkehrend`), { erfolg: "Betragsfilter entfernt." }); }
        catch (f) { /* gemeldet */ }
      } }))));
  return abschnitt("Wiederkehrende Buchungen",
    h("p", { class: "klein" }, "Zahlungen eines Empfängers, deren Betrag nicht passt (z. B. Auslagenerstattungen neben dem Gehalt), "
      + "werden bei der Erkennung übergangen und unterbrechen eine Serie nicht."),
    h("div", { class: "formular-zeile" }, feld("Vorgabe für alle Empfänger", modus), fProzent, speichern),
    h("h3", null, "Eigene Einstellungen je Empfänger"),
    zeilen.length ? tabelle({ tid: "wk-filter-liste" }, ["Empfänger", "Betragsfilter", h("span", { class: "nur-sr" }, "Aktionen")], zeilen)
      : leer("Alle Empfänger verwenden die Vorgabe."),
    knopf("Empfänger hinzufügen …", { tid: "wk-filter-neu", onclick: (e) => wkFilterDialog(null, e.currentTarget) }));
}

// ------------------------------------------------------------------ Einstellungen (13.2)
export async function einstellungen(seite, _p, _s, kontext) {
  const [status, sync, geheim, zust, postfaecher, wk] = await Promise.all([api("GET", "/api/status"), api("GET", "/api/sync/status"),
    api("GET", "/api/geheimnisse"), api("GET", "/api/benachrichtigungen/zustellung"), api("GET", "/api/mail/postfaecher"),
    api("GET", "/api/wiederkehrend/einstellungen")]);
  kopf(seite, "Einstellungen");
  // Darstellung
  const thema = h("select", { tid: "einstellung-thema" }, [["system", "wie System"], ["hell", "Hell"], ["dunkel", "Dunkel"]]
    .map(([w, t]) => h("option", { value: w }, t)));
  thema.value = kontext.thema.lesen();
  thema.addEventListener("change", () => kontext.thema.setzen(thema.value));
  seite.append(abschnitt("Darstellung", feld("Design", thema),
    knopf("Layout zurücksetzen", { tid: "layout-zuruecksetzen", onclick: () => { layoutZuruecksetzen(); melde("erfolg", "Layout zurückgesetzt."); } })));
  seite.append(wkFilterAbschnitt(wk));
  // Betrieb
  seite.append(abschnitt("Betrieb", h("p", { tid: "status-modus", "data-modus": status.modus },
    status.modus === "mock" ? "Mock-Modus" : "Echtbetrieb", ` · Version ${status.version}`,
    status.mock_szenario ? ` · Szenario ${status.mock_szenario}` : "")));
  // Benachrichtigungen
  const testErgebnis = h("p", { tid: "benachrichtigung-test-ergebnis", "aria-live": "polite", hidden: true });
  const test = knopf("Test-Benachrichtigung senden", { tid: "benachrichtigung-test", disabled: zust.plugin === "keins",
    onclick: async (e) => {
      const k = e.currentTarget;
      k.disabled = true;
      try {
        const r = await api("POST", "/api/benachrichtigungen/test");
        testErgebnis.dataset.zugestellt = r.zugestellt ? "ja" : "nein";
        testErgebnis.dataset.gesendet = r.gesendet ? "ja" : "nein";
        testErgebnis.textContent = r.zugestellt
          ? (r.gesendet ? "Test-Benachrichtigung zugestellt." : "Mock-Modus: bestätigt, es wurde nichts übertragen.")
          : `Zustellung fehlgeschlagen: ${r.fehler.meldung} (HTTP-Status ${r.fehler.status ?? "keiner"}).`;
      } catch (f) {
        testErgebnis.dataset.zugestellt = "nein";
        testErgebnis.dataset.gesendet = "nein";
        testErgebnis.textContent = `Fehler: ${f.message} (HTTP-Status ${f.status}).`;
      } finally { k.disabled = false; testErgebnis.hidden = false; }
    } });
  seite.append(abschnitt("Benachrichtigungen", h("p", { tid: "zustellung-status", "data-plugin": zust.plugin },
    `Zustellung über: ${zust.plugin} · ausstehend ${zust.ausstehend}, zugestellt ${zust.zugestellt}, aufgegeben ${zust.aufgegeben}`),
  zust.letzter_fehler ? h("p", { class: "klein" }, "Letzter Fehler: ", zust.letzter_fehler.meldung || "") : null, test, testErgebnis));
  // PIN
  seite.append(abschnitt("Bank-PIN", h("p", { tid: "pin-status", "data-vorhanden": sync.pin_vorhanden ? "ja" : "nein" },
    sync.pin_vorhanden ? "Die PIN liegt im Arbeitsspeicher des Servers." : "Keine PIN im Arbeitsspeicher."),
  knopf("PIN verwerfen", { tid: "pin-verwerfen", disabled: !sync.pin_vorhanden, onclick: async () => {
    try { await api("DELETE", "/api/sync/pin"); melde("erfolg", "PIN verworfen."); await oberflaeche.neuLaden(); }
    catch (e) { melde("fehler", e.message); }
  } })));
  // D-129: Schutz der Geheimnisse mit dem Login-Passwort
  seite.append(await schutzAbschnitt());
  // Geheimnisse
  const gesetzt = new Set(geheim.eintraege.map((e) => e.name));
  seite.append(abschnitt("Geheimnisse", ...[["ntfy_token", "ntfy-Token"], ["oauth_client_secret", "OAuth-Client-Secret"]].map(([n, t]) => {
    const wert = h("input", { type: "password", tid: `geheimnis-wert-${n}`, autocomplete: "off", value: "" });
    return h("div", { class: "geheimnis", tid: `geheimnis-${n}`, "data-gesetzt": gesetzt.has(n) ? "ja" : "nein" },
      feld(`${t} (${gesetzt.has(n) ? "gesetzt" : "nicht gesetzt"})`, wert),
      knopf("Speichern", { tid: `geheimnis-speichern-${n}`, "aria-label": `${t} speichern`, onclick: async () => {
        const w = wert.value;
        wert.value = "";
        if (!w) { melde("fehler", "Bitte einen Wert eingeben."); return; }
        try { await api("PUT", `/api/geheimnisse/${n}`, { wert: w }); melde("erfolg", `${t} gespeichert.`); await oberflaeche.neuLaden(); }
        catch (e) { melde("fehler", e.message); }
      } }),
      knopf("Löschen", { tid: `geheimnis-loeschen-${n}`, "aria-label": `${t} löschen`, onclick: async () => {
        try { await api("DELETE", `/api/geheimnisse/${n}`); melde("erfolg", `${t} gelöscht.`); await oberflaeche.neuLaden(); }
        catch (e) { melde("fehler", e.message); }
      } }));
  })));
  // Sicherung
  const datei = h("input", { type: "file", tid: "sicherung-datei", accept: ".zip,application/zip" });
  const sAusgabe = h("div", { "aria-live": "polite" });
  const senden = (params) => {
    const fd = new FormData();
    fd.append("datei", datei.files[0], datei.files[0].name);
    return api("POST", "/api/sicherung/einspielen" + abfrage(params), undefined, { formular: fd });
  };
  const einspielen = knopf("Einspielen …", { tid: "sicherung-einspielen", class: "knopf knopf-gefahr", disabled: true,
    onclick: async (e) => {
      if (!(await bestaetigen("Den gesamten Buchbestand durch die Sicherung ersetzen?", { ja: "Bestand ersetzen", ausloeser: e.currentTarget }))) return;
      try {
        await aktion(() => senden({ bestaetigt: true }), { erfolg: "Sicherung eingespielt." });
      } catch (f) { /* gemeldet */ }
    } });
  const pruefen = knopf("Prüfen", { tid: "sicherung-pruefen", onclick: async () => {
    if (!datei.files.length) { melde("fehler", "Bitte zuerst eine Sicherungsdatei wählen."); return; }
    try {
      const r = await senden({ trocken: true });
      sAusgabe.replaceChildren(h("p", null, r.geaendert ? "Die Sicherung ist gültig; Einspielen ersetzt den Bestand."
        : "Die Sicherung ist identisch mit dem Bestand.", ` (erstellt ${zeitText(r.manifest.erstellt)})`));
      einspielen.disabled = !r.geaendert;
    } catch (f) { sAusgabe.replaceChildren(h("p", { class: "fehler", role: "alert" }, f.message)); einspielen.disabled = true; }
  } });
  seite.append(abschnitt("Datensicherung", h("p", null, h("a", { tid: "sicherung-herunterladen", href: "/api/sicherung", download: "",
    class: "knopf" }, "Sicherung herunterladen")), feld("Sicherungsdatei", datei), knopfLeiste(pruefen, einspielen), sAusgabe));
  // Postfächer
  const adresse = h("input", { type: "email", maxlength: "320", autocomplete: "off" });
  seite.append(abschnitt("Mail-Postfächer", h("ul", { tid: "postfaecher" }, postfaecher.map((p) => h("li", null,
    h("a", { href: `/mail/postfaecher/${p.id}` }, p.adresse), p.bezeichnung ? ` (${p.bezeichnung})` : ""))),
  postfaecher.length ? null : leer("Kein Postfach eingerichtet."),
  h("div", { class: "formular-zeile" }, feld("Neues Postfach (Adresse)", adresse), knopf("Anlegen", { onclick: async () => {
    try { await aktion(() => api("POST", "/api/mail/postfaecher", { adresse: adresse.value.trim() }), { erfolg: "Postfach angelegt." }); }
    catch (e) { /* gemeldet */ }
  } })), knopf("Mails jetzt abrufen", { onclick: async () => {
    try { await api("POST", "/api/mail/abruf"); melde("erfolg", "Mails abgerufen."); } catch (e) { melde("fehler", e.message); }
  } })));
  // Tags
  seite.append(abschnitt("Tags", stamm.tags.length ? h("ul", null, stamm.tags.slice().sort(nachName).map((t) => h("li", null,
    `${t.name} (${t.anzahl_buchungen} Buchungen) `,
    knopf("Umbenennen…", { "aria-label": `Tag ${t.name} umbenennen`, onclick: (e) => dialog("tag-dialog", `Tag „${t.name}“ umbenennen`, (inhalt, d) => {
      const n = h("input", { type: "text", value: t.name, maxlength: "200" });
      const ok = knopf("Speichern", { class: "knopf knopf-haupt" });
      ok.addEventListener("click", () => imDialog(d, ok, () => aktion(() => api("PATCH", `/api/tags/${t.id}`, { name: n.value.trim() }),
        { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Tag umbenannt." })));
      inhalt.append(feld("Name", n), knopfLeiste(ok, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
    }, { ausloeser: e.currentTarget }) }),
    knopf("Löschen", { "aria-label": `Tag ${t.name} löschen`, onclick: async (e) => {
      if (!(await bestaetigen(`Tag „${t.name}“ löschen?`, { ja: "Löschen", ausloeser: e.currentTarget }))) return;
      try { await aktion(() => api("DELETE", `/api/tags/${t.id}`), { erfolg: "Tag gelöscht." }); } catch (f) { /* gemeldet */ }
    } })))) : leer("Noch keine Tags.")));
  // Anmeldung (19)
  if (anmeldung.aktiv) {
    const alt = h("input", { type: "password", autocomplete: "current-password" });
    const neu = h("input", { type: "password", autocomplete: "new-password" });
    seite.append(abschnitt("Anmeldung", h("div", { class: "formular-zeile" }, feld("Bisheriges Passwort", alt),
      feld("Neues Passwort", neu), knopf("Passwort ändern", { onclick: async () => {
        try { await api("PUT", "/api/anmeldung/passwort", { altes_passwort: alt.value, neues_passwort: neu.value }); melde("erfolg", "Passwort geändert."); }
        catch (e) { melde("fehler", e.message); } finally { alt.value = ""; neu.value = ""; }
      } })), knopf("Abmelden", { tid: "abmelden", onclick: () => kontext.abmelden() })));
  }
  return { titel: "Einstellungen" };
}

// ------------------------------------------------------------------ Protokoll (13.9)
const QUELLEN = { manuell: "manuell", import: "Import", sync: "Synchronisation", regel: "Regel", rueckgaengig: "Rückgängig",
  planer: "Planer", system: "System", sicherung: "Sicherung" };

export async function protokoll(seite) {
  kopf(seite, "Änderungsprotokoll");
  const liste = h("ol", { class: "protokoll", tid: "protokoll-liste" });
  const mehr = knopf("Ältere laden", { tid: "protokoll-mehr", hidden: true });
  let seiteNr = 0;
  let geladen = [];
  async function laden(n) {
    const s = await api("GET", `/api/aenderungen?pro_seite=50&seite=${n}`);
    return s;
  }
  function zeichnen(gesamt) {
    liste.replaceChildren(...geladen.map((a) => {
      const wirksam = a.rueckgaengig_durch === null;       // protokoll.md 3
      return h("li", { tid: `aenderung-${a.id}`, "data-id": String(a.id), "data-quelle": a.quelle, "data-wirksam": wirksam ? "ja" : "nein",
        class: "aenderung" + (wirksam ? "" : " unwirksam") },
      zeitEl("span", a.zeitpunkt, { class: "zeit" }), " ", h("span", { class: "marke" }, QUELLEN[a.quelle] || a.quelle), " ",
      h("span", null, a.beschreibung),
      a.rueckgaengig_durch ? h("span", { class: "klein" }, ` (rückgängig gemacht durch #${a.rueckgaengig_durch})`) : null,
      wirksam ? knopf("Rückgängig", { tid: `aenderung-rueckgaengig-${a.id}`,
        "aria-label": `Änderung ${a.id} rückgängig machen`, onclick: async () => {
          try { await api("POST", `/api/aenderungen/${a.id}/rueckgaengig`); melde("erfolg", "Rückgängig gemacht."); await oberflaeche.neuLaden(); }
          catch (e) { melde("fehler", e.message); }
        } }) : null,
      bisKnopf(a));
    }));
    mehr.hidden = geladen.length >= gesamt;
  }
  // Rückgängig bis hierher (D-108): alle Änderungen ab dieser (einschließlich) in einem Schritt
  function markieren(id) {
    for (const li of liste.children) li.classList.toggle("bis-markiert", id !== null && Number(li.dataset.id) >= id);
  }
  function bisKnopf(a) {
    const neuer = geladen.filter((x) => x.id >= a.id && x.rueckgaengig_durch === null).length;
    if (!neuer) return null;
    const k = knopf("Bis hierher rückgängig", { tid: `aenderung-bis-${a.id}`, class: "knopf knopf-klein",
      "aria-label": `Alle Änderungen bis einschließlich ${a.id} rückgängig machen`, onclick: async () => {
        markieren(a.id);
        const ok = await bestaetigen(`Alle Änderungen seit „${a.beschreibung}“ (${zeitText(a.zeitpunkt)}) einschließlich `
          + "dieser rückgängig machen? Das ergibt eine einzige neue Änderung, die sich ebenfalls wieder rückgängig machen lässt.",
        { ja: "Bis hierher rückgängig", ausloeser: k });
        markieren(null);
        if (!ok) return;
        try {
          const u = await api("POST", "/api/aenderungen/rueckgaengig", { bis_id: a.id });
          melde("erfolg", `${u.rueckgaengig_von.length === 1 ? "1 Änderung" : `${u.rueckgaengig_von.length} Änderungen`} rückgängig gemacht.`);
          await oberflaeche.neuLaden();
        } catch (e) { melde("fehler", e.message); }
      } });
    k.addEventListener("mouseenter", () => markieren(a.id));
    k.addEventListener("mouseleave", () => markieren(null));
    k.addEventListener("focus", () => markieren(a.id));
    k.addEventListener("blur", () => markieren(null));
    return k;
  }
  mehr.addEventListener("click", async () => {
    const s = await laden(seiteNr + 1);
    seiteNr += 1;
    geladen = geladen.concat(s.eintraege);
    zeichnen(s.gesamt);
  });
  const s = await laden(1);
  seiteNr = 1;
  geladen = s.eintraege;
  zeichnen(s.gesamt);
  seite.append(...[liste, geladen.length ? null : leer("Noch keine Änderungen."), mehr].filter(Boolean));
  return { titel: "Änderungsprotokoll" };
}

// ------------------------------------------------------------------ Empfänger (13.10)
export async function empfaenger(seite) {
  const liste = stamm.empfaenger;
  const auswahl = new Set();
  const zusammen = knopf("Zusammenführen…", { tid: "empfaenger-zusammenfuehren", disabled: true,
    onclick: (e) => zusammenfuehren(liste.filter((x) => auswahl.has(x.id)), e.currentTarget) });
  const pruefen = () => { zusammen.disabled = auswahl.size < 2; };   // 22.3: ab zwei ausgewählten
  kopf(seite, "Empfänger", zusammen);
  seite.append(liste.length ? tabelle({ class: "tabelle" }, ["", "Name", "Aliase", "Standardkategorie", ""], liste.map((e) => {
    const wahl = h("input", { type: "checkbox", tid: `empfaenger-auswahl-${e.id}`, "aria-label": `${e.name} auswählen` });
    wahl.addEventListener("change", () => { if (wahl.checked) auswahl.add(e.id); else auswahl.delete(e.id); pruefen(); });
    return h("tr", { tid: `empfaenger-${e.id}` },
      h("td", null, wahl), h("td", null, e.name), h("td", null, (e.aliase || []).join(", ")),
      h("td", null, e.standardkategorie_id ? pfadVon(e.standardkategorie_id) : ""),
      h("td", null, knopf("Bearbeiten…", { "aria-label": `Empfänger ${e.name} bearbeiten`, onclick: (ev) => empfaengerDialog(e, ev.currentTarget) })));
  }))
    : leer("Noch keine Empfänger."));
  return { titel: "Empfänger" };
}

function empfaengerDialog(e, ausloeser) {
  dialog("empfaenger-dialog", `Empfänger „${e.name}“`, (inhalt, d) => {
    const name = h("input", { type: "text", value: e.name, maxlength: "200" });
    const aliase = h("input", { type: "text", value: (e.aliase || []).join(", ") });
    const kat = h("select", null, h("option", { value: "" }, "– keine –"),
      kategorien().map(({ konto }) => h("option", { value: String(konto.id), selected: konto.id === e.standardkategorie_id }, kontoPfad(konto))));
    const speichern = knopf("Speichern", { class: "knopf knopf-haupt" });
    speichern.addEventListener("click", () => imDialog(d, speichern, async () => {
      const body = { name: name.value.trim(), aliase: aliase.value.split(",").map((x) => x.trim()).filter(Boolean),
        standardkategorie_id: kat.value ? Number(kat.value) : null };
      await aktion(() => api("PATCH", `/api/empfaenger/${e.id}`, body), { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Empfänger gespeichert." });
    }));
    inhalt.append(feld("Name", name), feld("Aliase (durch Komma getrennt)", aliase), feld("Standardkategorie", kat),
      knopfLeiste(speichern, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

// Vergleichsschlüssel für die Vorschau (wie `ekey` des Servers: Groß-/Kleinschreibung und Leerraum egal).
const vergleich = (t) => (t || "").normalize("NFKC").toLowerCase().replace(/\s+/g, " ").trim();

/** Aliase nach dem Zusammenführen (buchhaltungspflege.md 2.4, 10) – nur als Vorschau, maßgeblich ist der Server. */
function aliasVorschau(ziel, quellen, name) {
  const neu = name !== ziel.name;
  const zielKey = vergleich(neu ? name : ziel.name);
  const gesehen = new Set();
  const aus = [];
  const kandidaten = [...(ziel.aliase || []), ...(neu ? [ziel.name] : []),
    ...quellen.slice().sort((a, b) => a.id - b.id).flatMap((q) => [q.name, ...(q.aliase || [])])];
  for (const k of kandidaten) {
    const key = vergleich(k);
    if (!key || key === zielKey || gesehen.has(key)) continue;
    gesehen.add(key);
    aus.push(k);
  }
  return aus.sort();
}

/** 22.3: Ziel (vorbelegt mit den meisten Buchungen), neuer Name, Vorschau der Aliase. */
function zusammenfuehren(gewaehlt, ausloeser) {
  dialog("zusammenfuehren-dialog", "Empfänger zusammenführen", (inhalt, d) => {
    const ziel = h("select", { tid: "zusammenfuehren-ziel" },
      gewaehlt.map((e) => h("option", { value: String(e.id) }, e.name)));
    const name = h("input", { type: "text", tid: "zusammenfuehren-name", maxlength: "200", value: gewaehlt[0].name });
    const vorschau = h("ul", { tid: "zusammenfuehren-aliase", class: "alias-vorschau", "aria-live": "polite" });
    let nameGeaendert = false;
    const zielObj = () => gewaehlt.find((e) => String(e.id) === ziel.value) || gewaehlt[0];
    const zeigen = () => {
      const z = zielObj();
      const aliase = aliasVorschau(z, gewaehlt.filter((e) => e.id !== z.id), name.value.trim() || z.name);
      vorschau.replaceChildren(...(aliase.length ? aliase.map((a) => h("li", null, a)) : [h("li", { class: "leer" }, "keine")]));
    };
    const zielSetzen = (id) => {
      ziel.value = String(id);
      if (!nameGeaendert) name.value = zielObj().name;
      zeigen();
    };
    ziel.addEventListener("change", () => zielSetzen(ziel.value));
    name.addEventListener("input", () => { nameGeaendert = true; zeigen(); });
    zeigen();
    // Buchungszahl je Empfänger; Ziel = meiste Buchungen, bei Gleichstand kleinste id
    Promise.all(gewaehlt.map((e) => api("GET", `/api/buchungen${abfrage({ empfaenger_id: e.id, pro_seite: 1 })}`)
      .then((r) => [e.id, r.gesamt]).catch(() => [e.id, 0]))).then((zahlen) => {
      if (!d.offen) return;
      zahlen.sort((a, b) => b[1] - a[1] || a[0] - b[0]);
      zielSetzen(zahlen[0][0]);
    });
    const los = knopf("Zusammenführen", { class: "knopf knopf-haupt", tid: "zusammenfuehren-ausfuehren" });
    los.addEventListener("click", () => imDialog(d, los, async () => {
      const z = zielObj();
      const body = { quelle_ids: gewaehlt.filter((e) => e.id !== z.id).map((e) => e.id) };
      const neuerName = name.value.trim();
      if (neuerName !== z.name) body.name = neuerName;
      await aktion(() => api("POST", `/api/empfaenger/${z.id}/zusammenfuehren`, body),
        { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Empfänger zusammengeführt." });
    }));
    inhalt.append(feld("Ziel (bleibt bestehen)", ziel), feld("Neuer Name", name),
      h("div", { class: "feld" }, h("span", null, "Suchtexte (Aliase) danach"), vorschau),
      knopfLeiste(los, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

// ------------------------------------------------------------------ Regeln, Vorlagen (13.10)
const BED_TEXT = (b) => `${b.feld} ${b.operator} ${b.wert ?? b.konto_id ?? ""}`;

export async function regeln(seite) {
  const liste = await api("GET", "/api/regeln");
  kopf(seite, "Regeln", knopf("Regeln anwenden", { tid: "regeln-anwenden", onclick: async () => {
    try {
      const r = await aktion(() => api("POST", "/api/regeln/anwenden", {}), { erfolg: "Regeln angewendet." });
      if (r && r.geaendert !== undefined) melde("hinweis", `${r.geaendert} Buchungen geändert.`);
    } catch (e) { /* gemeldet */ }
  } }), knopf("Lernmodell anwenden", { onclick: async () => {
    try { await aktion(() => api("POST", "/api/lernmodell/anwenden", {}), { erfolg: "Lernmodell angewendet." }); } catch (e) { /* gemeldet */ }
  } }));
  seite.querySelector(".werkzeuge").prepend(knopf("Regel anlegen", { tid: "regel-anlegen", onclick: (e) => regelDialog(null, e.currentTarget) }));
  seite.append(liste.length ? h("ul", { class: "karten-liste" }, liste.map((r) => h("li", { tid: `regel-${r.id}`, class: "karte" },
    h("strong", null, r.name), ` → ${pfadVon(r.kategorie_id)} · Priorität ${r.prioritaet}${r.aktiv ? "" : " · inaktiv"}`,
    h("ul", { class: "klein" }, r.bedingungen.map((b) => h("li", null, BED_TEXT(b)))),
    knopfLeiste(knopf("Bearbeiten…", { "aria-label": `Regel ${r.name} bearbeiten`, onclick: (e) => regelDialog(r, e.currentTarget) }),
      knopf("Löschen", { "aria-label": `Regel ${r.name} löschen`, onclick: async (e) => {
        if (!(await bestaetigen(`Regel „${r.name}“ löschen?`, { ja: "Löschen", ausloeser: e.currentTarget }))) return;
        try { await aktion(() => api("DELETE", `/api/regeln/${r.id}`), { erfolg: "Regel gelöscht." }); } catch (f) { /* gemeldet */ }
      } }))))) : leer("Noch keine Regeln."));
  return { titel: "Regeln" };
}

export async function vorlagen(seite) {
  const liste = await api("GET", "/api/vorlagen");
  kopf(seite, "Split-Vorlagen", knopf("Vorlagen anwenden", { tid: "vorlagen-anwenden", onclick: async () => {
    try { await aktion(() => api("POST", "/api/vorlagen/anwenden", {}), { erfolg: "Vorlagen angewendet." }); } catch (e) { /* gemeldet */ }
  } }));
  seite.append(liste.length ? h("ul", { class: "karten-liste" }, liste.map((v) => h("li", { tid: `vorlage-${v.id}`, class: "karte" },
    h("strong", null, v.name), " · Gesamtbetrag ", betragEl("span", v.gesamtbetrag),
    h("ul", { class: "klein" }, v.teile.map((t) => h("li", null, `${pfadVon(t.konto_id)}: `,
      t.betrag !== undefined && t.betrag !== null ? betragEl("span", t.betrag) : (t.rest ? "Rest" : ""), t.memo ? ` – ${t.memo}` : "")))))) : leer("Noch keine Split-Vorlagen."));
  return { titel: "Split-Vorlagen" };
}

/** Bedingungen als Zeilen „feld operator wert“ (Text: empfaenger/verwendungszweck; Betrag in Euro). */
function regelDialog(r, ausloeser) {
  dialog("regel-dialog", r ? `Regel „${r.name}“` : "Regel anlegen", (inhalt, d) => {
    const name = h("input", { type: "text", maxlength: "200", value: r ? r.name : "" });
    const kat = h("select", null, kategorien().map(({ konto }) => h("option", { value: String(konto.id),
      selected: r && konto.id === r.kategorie_id }, kontoPfad(konto))));
    const prio = h("input", { type: "number", step: "1", value: String(r ? r.prioritaet : 100) });
    const aktiv = h("input", { type: "checkbox", checked: r ? r.aktiv : true });
    const bed = h("textarea", { rows: "4", spellcheck: "false" });
    bed.value = r ? r.bedingungen.map((b) => (b.feld === "betrag" ? `betrag ${b.operator} ${betragEingabeText(b.wert)}`
      : `${b.feld} ${b.operator} ${b.wert}`)).join("\n") : "empfaenger enthaelt ";
    const speichern = knopf("Speichern", { class: "knopf knopf-haupt" });
    speichern.addEventListener("click", () => imDialog(d, speichern, async () => {
      const bedingungen = bed.value.split("\n").map((z) => z.trim()).filter(Boolean).map((z) => {
        const [feld, operator, ...rest] = z.split(/\s+/);
        const wert = rest.join(" ");
        return feld === "betrag" ? { feld, operator, wert: betragLesen(wert) } : { feld, operator, wert };
      });
      const body = { name: name.value.trim(), kategorie_id: Number(kat.value), prioritaet: Number(prio.value), aktiv: aktiv.checked,
        bedingungen };
      await aktion(() => (r ? api("PATCH", `/api/regeln/${r.id}`, body) : api("POST", "/api/regeln", body)),
        { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Regel gespeichert." });
    }));
    inhalt.append(feld("Name", name), feld("Kategorie", kat), feld("Priorität", prio), h("label", { class: "wahl" }, aktiv, " aktiv"),
      feld("Bedingungen (je Zeile: Feld Operator Wert, z. B. „empfaenger enthaelt Bäckerei“ oder „betrag hoechstens -10,00“)", bed),
      knopfLeiste(speichern, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

function betragEingabeText(c) {
  const neg = c < 0;
  const a = Math.abs(c);
  return (neg ? "-" : "") + Math.trunc(a / 100) + "," + String(a % 100).padStart(2, "0");
}

// ------------------------------------------------------------------ Dubletten (13.10)
export async function dubletten(seite) {
  const liste = await api("GET", "/api/dubletten?status=offen");
  kopf(seite, "Dubletten", knopf("Umbuchungen erkennen", { onclick: async () => {
    try { await aktion(() => api("POST", "/api/umbuchungen/erkennen", {}), { erfolg: "Umbuchungen geprüft." }); } catch (e) { /* gemeldet */ }
  } }));
  const zeilen = await Promise.all(liste.map(async (v) => {
    const bs = await Promise.all([v.buchung_id, ...v.kandidat_ids].map((id) => api("GET", `/api/buchungen/${id}`).catch(() => null)));
    const aufloesen = async (body) => {
      try { await aktion(() => api("POST", `/api/dubletten/${v.id}/aufloesen`, body), { erfolg: "Dublettenverdacht aufgelöst." }); }
      catch (e) { /* gemeldet */ }
    };
    return h("li", { tid: `verdacht-${v.id}`, class: "karte" }, h("p", null, `Verdacht ${v.id} (${v.grund})`),
      h("ul", null, bs.filter(Boolean).map((b) => h("li", null, `${datumText(b.datum)} · ${b.empfaenger ? b.empfaenger.name : "ohne Empfänger"} · `,
        betragEl("span", b.betrag), " ", knopf("Diese behalten", { "aria-label": `Buchung ${b.id} behalten`,
          onclick: () => aufloesen({ entscheidung: "zusammenfuehren", behalten_id: b.id }) })))),
      knopf("Keine Dublette", { onclick: () => aufloesen({ entscheidung: "keine_dublette" }) }));
  }));
  seite.append(zeilen.length ? h("ul", { class: "karten-liste" }, zeilen) : leer("Keine offenen Dublettenverdachte."));
  return { titel: "Dubletten" };
}

// ------------------------------------------------------------------ Synchronisation (13.10)
const LAUFSTATUS = { laeuft: "läuft", erfolgreich: "erfolgreich", fehlgeschlagen: "fehlgeschlagen", wartet_auf_tan: "wartet auf TAN",
  abgebrochen: "abgebrochen" };

export async function syncSeite(seite, _p, _s, kontext) {
  const [st, laeufe, konten] = await Promise.all([api("GET", "/api/sync/status"), api("GET", "/api/sync/laeufe"),
    api("GET", "/api/sync/konten")]);
  kopf(seite, "Synchronisation", knopf("Jetzt synchronisieren", { onclick: () => kontext.synchronisieren() }));
  seite.append(abschnitt("Status", h("p", { tid: "sync-status", "data-laeuft": st.laeuft ? "ja" : "nein" },
    st.laeuft ? "Ein Lauf ist aktiv." : "Kein Lauf aktiv.", st.automatisch ? ` Automatisch alle ${st.intervall_minuten} Minuten.` : " Automatik aus.",
    st.naechster_lauf ? ` Nächster Lauf: ${zeitText(st.naechster_lauf)}.` : "",
    st.offene_tan_anforderung ? h("a", { href: `/tan/${st.offene_tan_anforderung.id}` }, " Offene TAN-Freigabe") : null)));
  seite.append(abschnitt("Bankkonten", konten.length ? h("ul", null, konten.map((k) => {
    const li = h("li", { tid: `bankkonto-${k.iban}`, "data-status": k.status || "aktiv" }, `${k.iban} → ${pfadVon(k.konto_id)}`,
      ` · ${k.status || "aktiv"}`, k.letzter_abruf_bis ? ` · abgerufen bis ${datumText(k.letzter_abruf_bis)}` : "",
      saldoAbgleich(k, laeufe));
    if (k.status === "konto_fehlt") {
      const entscheiden = async (body) => {
        try { await api("POST", `/api/sync/konten/${encodeURIComponent(k.iban)}/entscheidung`, body); melde("erfolg", "Entscheidung gespeichert."); await oberflaeche.neuLaden(); }
        catch (e) { melde("fehler", e.message); }
      };
      li.append(" ", knopf("Wiederherstellen (alle)", { onclick: () => entscheiden({ aktion: "wiederherstellen", buchungen: "alle" }) }),
        knopf("Wiederherstellen (nur neue)", { onclick: () => entscheiden({ aktion: "wiederherstellen", buchungen: "nur_neue" }) }),
        knopf("Ignorieren", { onclick: () => entscheiden({ aktion: "ignorieren", buchungen: "alle" }) }));
    }
    return li;
  })) : leer("Noch keine Bankkonten synchronisiert.")));
  // D-111: Bankkonten, die der letzte Lauf übersprungen hat, weil sie noch keinem Konto zugeordnet sind
  const letzter = laeufe.slice().sort((a, b) => b.id - a.id)[0];
  const offen = ((letzter && letzter.uebersprungen) || []).filter((u) => u.status === "nicht_zugeordnet"
    && !stamm.konten.some((k) => k.iban === u.iban));
  if (offen.length) {
    seite.append(abschnitt("Nicht zugeordnete Bankkonten", h("ul", { tid: "sync-nicht-zugeordnet" }, offen.map((u) =>
      h("li", { tid: `nicht-zugeordnet-${u.iban}` }, `${u.name || ""} · ${u.iban} `,
        knopf("Zuordnen…", { tid: `zuordnen-${u.iban}`, onclick: async (e) => {
          if (await zuordnungDialog(u, e.currentTarget)) await kontext.synchronisieren();
        } }))))));
  }
  if (st.jetzt && document.querySelector('[data-testid="mock-hinweis"]')) {
    const zeit = h("input", { type: "datetime-local", step: "1" });
    seite.append(abschnitt("Mock-Uhr", h("p", null, "Simulierte Zeit des Servers: ", zeitEl("span", st.jetzt)),
      h("div", { class: "formular-zeile" }, feld("Neue Zeit (UTC)", zeit), knopf("Setzen", { onclick: async () => {
        if (!zeit.value) return;
        try { await api("PUT", "/api/mock/zeit", { jetzt: (zeit.value.length === 16 ? zeit.value + ":00" : zeit.value) + "Z" }); await oberflaeche.neuLaden(); }
        catch (e) { melde("fehler", e.message); }
      } }))));
  }
  seite.append(abschnitt("Läufe", laeufe.length ? h("ul", { class: "laeufe" }, laeufe.slice().reverse().map((l) => h("li", { tid: `lauf-${l.id}`,
    "data-status": l.status }, zeitEl("span", l.gestartet_am), ` · ${LAUFSTATUS[l.status] || l.status}`,
  l.fehler ? ` · ${l.fehler.meldung || l.fehler.code}` : "",
  l.tan_anforderung_id && l.status === "wartet_auf_tan" ? h("a", { href: `/tan/${l.tan_anforderung_id}` }, " TAN eingeben") : null)))
    : leer("Noch keine Läufe.")));
  return { titel: "Synchronisation" };
}

// 22.4: Saldoabgleich des letzten Laufs, in dem das Bankkonto erfolgreich verarbeitet wurde (kontostand.md 2.1).
const SALDO_TEXT = { aus: "Kontostandsabgleich aus", nicht_verfuegbar: "Bank meldet keinen Kontostand",
  stimmt: "Kontostand stimmt", ausgeglichen: "Kontostand ausgeglichen" };
function saldoAbgleich(k, laeufe) {
  let sa = null;
  for (const l of laeufe.slice().sort((a, b) => b.id - a.id)) {
    const x = (l.konten || []).find((y) => y.iban === k.iban && y.status === "erfolgreich" && y.saldo_abgleich);
    if (x) { sa = { ...x.saldo_abgleich, konto_id: x.konto_id }; break; }
  }
  const el = h("span", { tid: "bankkonto-saldo", class: "bankkonto-saldo", "data-status": sa ? sa.status : "" });
  if (!sa) return el;
  el.append(" · ", SALDO_TEXT[sa.status] || sa.status);
  if (sa.status === "stimmt" || sa.status === "ausgeglichen") {
    el.append(": Bank ", betragEl("span", sa.bank_saldo), ` am ${datumText(sa.stichtag)}, Differenz `,
      betragEl("span", sa.differenz));
  }
  if (sa.status === "ausgeglichen") {
    el.append(" ", h("a", { href: `/konten/${sa.konto_id}`, tid: `bankkonto-ausgleich-${k.iban}` }, "Ausgleichsbuchung prüfen"));
  }
  return el;
}

// ------------------------------------------------------------------ Benachrichtigungen (13.10)
export async function benachrichtigungen(seite) {
  const liste = await api("GET", "/api/benachrichtigungen");
  kopf(seite, "Benachrichtigungen");
  seite.append(liste.length ? h("ul", { class: "karten-liste" }, liste.map((b) => h("li", { tid: `benachrichtigung-${b.id}`,
    "data-gelesen": b.gelesen ? "ja" : "nein", class: "karte" + (b.gelesen ? " gelesen" : "") },
  h("strong", null, b.titel), " ", zeitEl("span", b.erstellt_am, { class: "klein" }), h("p", null, b.text),
  b.link ? h("a", { href: b.link, tid: `benachrichtigung-link-${b.id}` }, "Öffnen") : null, " ",
  b.gelesen ? null : knopf("Als gelesen markieren", { tid: `benachrichtigung-gelesen-${b.id}`, onclick: async () => {
    try { await api("POST", `/api/benachrichtigungen/${b.id}/gelesen`); await oberflaeche.neuLaden(); await oberflaeche.benachrichtigungen(); }
    catch (e) { melde("fehler", e.message); }
  } })))) : leer("Keine Benachrichtigungen."));
  return { titel: "Benachrichtigungen" };
}

// ------------------------------------------------------------------ Suche (13.8)
export async function suche(seite, _p, suchtext) {
  const q = new URLSearchParams(suchtext).get("q") || "";
  kopf(seite, "Suche");
  if (!q.trim()) { seite.append(h("p", { tid: "suche-anzahl", "data-anzahl": "0" }, "Bitte einen Suchbegriff eingeben.")); return { titel: "Suche" }; }
  const e = await api("GET", "/api/suche" + abfrage({ q, limit: 200 }));
  const feldEl = tid("suche-feld");
  if (feldEl && document.activeElement !== feldEl) feldEl.value = q;
  seite.append(h("p", { tid: "suche-anzahl", "data-anzahl": String(e.buchungen_gesamt) }, `Suche nach „${q}“: ${e.buchungen_gesamt} Buchungen`));
  if (e.konten.length) seite.append(abschnitt("Konten", h("ul", null, e.konten.map((k) => h("li", { tid: `treffer-konto-${k.id}` },
    h("a", { href: `/konten/${k.id}` }, kontoPfad(k)))))));
  if (e.empfaenger.length) seite.append(abschnitt("Empfänger", h("ul", null, e.empfaenger.map((x) => h("li", { tid: `treffer-empfaenger-${x.id}` }, x.name)))));
  if (e.tags.length) seite.append(abschnitt("Tags", h("ul", null, e.tags.map((t) => h("li", { tid: `treffer-tag-${t.id}` }, t.name)))));
  const raster = h("div", { role: "grid", class: "buchungsliste treffer", "aria-label": "Gefundene Buchungen", "data-kompakt": "nein" },
    h("div", { role: "row", class: "liste-kopf" }, ["Datum", "Empfänger", "Verwendungszweck", "Kategorie", "Betrag"].map((t) => h("div", { role: "columnheader", class: "zelle" }, t))),
    e.buchungen.map((b) => {
      const z = h("div", { role: "row", tid: `buchung-${b.id}`, class: "zeile", tabindex: "0", "data-status": b.status, "aria-selected": "false" },
        datumEl("div", b.datum, { role: "gridcell", class: "zelle", "data-feld": "datum" }),
        h("div", { role: "gridcell", class: "zelle", "data-feld": "empfaenger" }, b.empfaenger ? b.empfaenger.name : ""),
        h("div", { role: "gridcell", class: "zelle", "data-feld": "verwendungszweck" }, b.verwendungszweck),
        h("div", { role: "gridcell", class: "zelle", "data-feld": "kategorie" }, b.kategorie_id ? pfadVon(b.kategorie_id) : ""),
        betragEl("div", b.betrag, { role: "gridcell", class: "zelle zahl", "data-feld": "betrag" }));
      const konto = b.splits.map((s) => kontoNach(s.konto_id)).find((k) => k && BESTAND.has(k.art));
      z.addEventListener("dblclick", () => { if (konto) oberflaeche.gehe(`/konten/${konto.id}`); });
      z.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && konto) oberflaeche.gehe(`/konten/${konto.id}`); });
      return z;
    }));
  seite.append(abschnitt("Buchungen", raster));
  return { titel: "Suche" };
}

// ------------------------------------------------------------------ TAN-Seite (14, K 6)
const ENDUNG = { "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif" };

export async function tan(seite, id, _s, kontext) {
  const a = await api("GET", `/api/tan-anforderungen/${id}`);
  kopf(seite, "TAN-Freigabe");
  seite.append(h("p", null, "Status: ", h("strong", { tid: "tan-status", "data-status": a.status }, TANSTATUS[a.status] || a.status),
    " · gültig bis ", zeitEl("span", a.gueltig_bis, { tid: "tan-gueltig-bis" })),
  h("p", { tid: "tan-challenge", class: "challenge" }, a.challenge));
  if (a.status !== "offen") return { titel: "TAN-Freigabe" };
  if (a.hat_bild) {
    const r = await api("GET", `/api/tan-anforderungen/${id}/bild`, undefined, { roh: true });
    const blob = await r.blob();
    const typ = blob.type || r.headers.get("content-type") || "application/octet-stream";
    const name = `kontor-tan-${id}.${ENDUNG[typ.split(";")[0].trim()] || "bin"}`;
    const url = URL.createObjectURL(blob);
    const datei = new File([blob], name, { type: typ.split(";")[0].trim() });
    const teilbar = typeof navigator.canShare === "function" && typeof navigator.share === "function"
      && (() => { try { return navigator.canShare({ files: [datei] }); } catch (e) { return false; } })();
    const speichern = knopf("QR-Code speichern", { tid: "tan-bild-speichern", onclick: () => {
      const link = h("a", { href: url, download: name, hidden: true });
      document.body.append(link);
      link.click();
      link.remove();
    } });
    const teilen = knopf("Teilen", { tid: "tan-bild-teilen", hidden: !teilbar, onclick: async () => {
      try { await navigator.share({ files: [datei], title: "TAN-Freigabe" }); }
      catch (e) { if (e && e.name !== "AbortError") melde("fehler", "Teilen ist fehlgeschlagen."); }
    } });
    seite.append(h("figure", { class: "tan-bild-rahmen" }, h("img", { tid: "tan-bild", src: url, alt: "QR-Code bzw. Grafik der TAN-Freigabe",
      class: "tan-bild" })), knopfLeiste(speichern, teilen));
  }
  const eingabe = h("input", { type: "text", tid: "tan-eingabe", autocomplete: "one-time-code", inputmode: "numeric", value: "",
    maxlength: "64", spellcheck: "false" });
  const fehler = h("p", { tid: "tan-fehler", role: "alert", class: "fehler", hidden: true });
  const senden = knopf("TAN senden", { tid: "tan-senden", class: "knopf knopf-haupt" });
  const absenden = async () => {
    const wert = eingabe.value.trim();
    eingabe.value = "";
    fehler.hidden = true;
    if (!wert) return;
    senden.disabled = true;
    try {
      const lauf = await api("POST", `/api/tan-anforderungen/${id}/antwort`, { tan: wert });
      await kontext.neuZeigen();
      const s = tid("seite-tan");
      if (s) s.append(h("p", { tid: "tan-ergebnis", "data-lauf-status": lauf.status }, `Synchronisation: ${LAUFSTATUS[lauf.status] || lauf.status}`));
    } catch (e) {
      if (e.code === "tan_ungueltig" || e.status === 422) { fehler.textContent = e.message || "Die TAN wurde abgelehnt."; fehler.hidden = false; eingabe.focus(); }
      else melde("fehler", e.message);
    } finally { senden.disabled = false; }
  };
  senden.addEventListener("click", absenden);
  eingabe.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); absenden(); } });
  const abbrechen = knopf("Abbrechen", { tid: "tan-abbrechen", onclick: async (e) => {
    if (!(await bestaetigen("Die TAN-Freigabe abbrechen?", { ja: "Freigabe abbrechen", ausloeser: e.currentTarget }))) return;
    try { await api("POST", `/api/tan-anforderungen/${id}/abbrechen`); await kontext.neuZeigen(); }
    catch (f) { melde("fehler", f.message); }
  } });
  seite.append(feld("TAN", eingabe), fehler, knopfLeiste(senden, abbrechen));
  return { titel: "TAN-Freigabe" };
}

const TANSTATUS = { offen: "offen", beantwortet: "beantwortet", abgelaufen: "abgelaufen", abgebrochen: "abgebrochen" };

// ------------------------------------------------------------------ Postfach (13.10)
const ANMELDESTATUS = { nicht_erforderlich: "keine Anmeldung nötig", fehlt: "nicht angemeldet", angemeldet: "angemeldet",
  abgelaufen: "abgelaufen", widerrufen: "widerrufen" };

export async function postfach(seite, id) {
  const [p, st] = await Promise.all([api("GET", `/api/mail/postfaecher/${id}`), api("GET", `/api/mail/postfaecher/${id}/status`)]);
  kopf(seite, p.adresse);
  const ort = h("div", { "aria-live": "polite" });
  const antwort = h("input", { type: "url", tid: "postfach-antwort-url", maxlength: "8192", autocomplete: "off" });
  seite.append(abschnitt("Status", h("p", { tid: "postfach-status", "data-anmeldung": st.anmeldung }, ANMELDESTATUS[st.anmeldung] || st.anmeldung,
    st.laeuft_ab_am ? ` · läuft ab am ${zeitText(st.laeuft_ab_am)}` : "", ` · ${st.nachrichten} Nachrichten`,
    st.letzter_fehler ? ` · letzter Fehler: ${st.letzter_fehler.meldung || st.letzter_fehler.code}` : "")),
  appPasswortAbschnitt(id, p),
  abschnitt("Anmeldung (OAuth2)", h("p", { class: "klein" }, "Alternative zum App-Passwort; braucht ein eigenes Google-Cloud-Projekt."), knopf("Anmeldung starten", { tid: "postfach-anmelden", onclick: async () => {
    try {
      const s = await api("POST", `/api/mail/postfaecher/${id}/anmeldung`);
      ort.replaceChildren(h("p", null, h("a", { tid: "postfach-autorisierung-link", href: s.autorisierung_url, target: "_blank",
        rel: "noopener noreferrer" }, "Anmeldung beim Mail-Anbieter öffnen"), ` (gültig bis ${zeitText(s.gueltig_bis)})`));
    } catch (e) { melde("fehler", e.message); }
  } }), ort, feld("Umleitungs-URL nach der Zustimmung", antwort),
  knopf("Anmeldung abschließen", { tid: "postfach-abschliessen", onclick: async () => {
    try { await api("POST", "/api/mail/anmeldung/abschluss", { antwort_url: antwort.value.trim() }); antwort.value = ""; melde("erfolg", "Postfach angemeldet."); await oberflaeche.neuLaden(); }
    catch (e) { melde("fehler", e.message); }
  } })));
  return { titel: p.adresse };
}

// D-130: Zugang mit App-Passwort und Ordner (Gmail-Label), nur lesend
function appPasswortAbschnitt(id, p) {
  const ordner = h("input", { tid: "postfach-ordner", value: p.ordner, maxlength: "200" });
  const pw = h("input", { type: "password", tid: "postfach-app-passwort", autocomplete: "off", spellcheck: "false" });
  const ergebnis = h("p", { tid: "postfach-app-ergebnis", role: "status", "aria-live": "polite" });
  const speichern = knopf("Speichern und Verbindung testen", { tid: "postfach-app-speichern", class: "knopf knopf-haupt",
    onclick: async (e) => {
      const wert = pw.value;
      pw.value = "";
      if (!wert) { melde("fehler", "Bitte das App-Passwort eingeben."); return; }
      e.currentTarget.disabled = true;
      ergebnis.textContent = "Verbinde mit dem Mailserver …";
      try {
        if (ordner.value.trim() && ordner.value.trim() !== p.ordner) {
          await api("PATCH", `/api/mail/postfaecher/${id}`, { ordner: ordner.value.trim() });
        }
        const r = await api("PUT", `/api/mail/postfaecher/${id}/app-passwort`, { passwort: wert });
        melde("erfolg", `Verbunden: ${r.nachrichten_im_ordner} Nachricht(en) im Ordner „${r.ordner}“.`);
        await oberflaeche.neuLaden();
      } catch (f) { ergebnis.textContent = `Fehler: ${f.message}`; }
      finally { e.currentTarget.disabled = false; }
    } });
  const entfernen = knopf("App-Passwort entfernen", { tid: "postfach-app-entfernen", onclick: async () => {
    try { await api("DELETE", `/api/mail/postfaecher/${id}/app-passwort`); melde("erfolg", "App-Passwort entfernt."); await oberflaeche.neuLaden(); }
    catch (f) { melde("fehler", f.message); }
  } });
  return abschnitt("Zugang mit App-Passwort (empfohlen für Gmail)",
    h("ol", { class: "klein" },
      h("li", null, "Im Google-Konto die Bestätigung in zwei Schritten einschalten."),
      h("li", null, "Google-Konto → Sicherheit → App-Passwörter: ein Passwort „Kontor“ erzeugen."),
      h("li", null, "In Gmail einen Filter anlegen, der Mails von Amazon und PayPal mit dem Label „Kontor“ versieht."),
      h("li", null, "Hier Label und App-Passwort eintragen. Kontor öffnet nur diesen Ordner und nur lesend.")),
    feld("Ordner bzw. Gmail-Label", ordner), feld("App-Passwort (16 Zeichen, Leerzeichen egal)", pw),
    h("div", { class: "knopf-leiste" }, speichern, entfernen), ergebnis);
}

// ------------------------------------------------------------------ Buchung (Link aus split_abweichung)
export async function buchung(seite, id) {
  const b = await api("GET", `/api/buchungen/${id}`);
  kopf(seite, `Buchung vom ${datumText(b.datum)}`);
  const konto = b.splits.map((s) => kontoNach(s.konto_id)).find((k) => k && BESTAND.has(k.art));
  seite.append(abschnitt("Einzelheiten", h("p", null, b.empfaenger ? b.empfaenger.name : "ohne Empfänger", " · ", b.verwendungszweck,
    " · ", STATUS_TEXT[b.status]), h("ul", null, b.splits.map((s) => h("li", null, pfadVon(s.konto_id), " ", betragEl("span", s.betrag),
    s.memo ? ` – ${s.memo}` : ""))), konto ? h("p", null, h("a", { href: `/konten/${b.splits[0] && konto.id}` }, `Im Konto „${konto.name}“ anzeigen`)) : null));
  return { titel: `Buchung vom ${datumText(b.datum)}` };
}

export const _intern = { nachName, neueId };

// ------------------------------------------------------------------ D-129: Schutz der Geheimnisse
async function schutzAbschnitt() {
  let st;
  try { st = await api("GET", "/api/geheimnisse/schutz"); } catch { return h("div"); }
  const pw = h("input", { type: "password", tid: "schutz-passwort", autocomplete: "current-password" });
  const mitPasswort = (pfad, erfolg) => async () => {
    const wert = pw.value;
    pw.value = "";
    if (!wert) { melde("fehler", "Bitte das Login-Passwort eingeben."); return; }
    try { await api("POST", pfad, { passwort: wert }); melde("erfolg", erfolg); window.dispatchEvent(new Event("kontor-sperre")); await oberflaeche.neuLaden(); }
    catch (e) { melde("fehler", e.message); }
  };
  const text = !st.aktiv
    ? "Aus: Geheimnisse sind nur mit dem Systemschlüssel verschlüsselt. Eingeschaltet schützt das Login-Passwort Bank-PIN und Mail-Zugänge zusätzlich – auch in Snapshots der Festplatte. Nach jedem Neustart muss Kontor dann einmal entsperrt werden (beim Login automatisch)."
    : st.entsperrt ? `Ein und entsperrt: ${st.geschuetzt} Geheimnis(se) mit dem Login-Passwort geschützt${st.pin_gemerkt ? ", Bank-PIN gemerkt" : ""}.`
      : "Ein, aber gesperrt: Bankabruf und Mail-Abgleich warten auf das Entsperren.";
  const knoepfe = !st.aktiv
    ? [knopf("Schutz einschalten", { tid: "schutz-einschalten", class: "knopf knopf-haupt",
      onclick: mitPasswort("/api/geheimnisse/schutz", "Die Geheimnisse sind jetzt mit dem Login-Passwort geschützt.") })]
    : [st.entsperrt
      ? knopf("Jetzt sperren", { tid: "schutz-sperren", onclick: async () => {
        try { await api("POST", "/api/geheimnisse/sperren", {}); melde("erfolg", "Gesperrt."); window.dispatchEvent(new Event("kontor-sperre")); await oberflaeche.neuLaden(); }
        catch (e) { melde("fehler", e.message); }
      } })
      : knopf("Entsperren", { tid: "schutz-entsperren", class: "knopf knopf-haupt",
        onclick: mitPasswort("/api/geheimnisse/entsperren", "Entsperrt.") }),
    st.pin_gemerkt ? knopf("Gemerkte PIN vergessen", { tid: "schutz-pin-vergessen", onclick: async () => {
      try { await api("DELETE", "/api/sync/pin/gemerkt"); melde("erfolg", "Gemerkte PIN gelöscht."); await oberflaeche.neuLaden(); }
      catch (e) { melde("fehler", e.message); }
    } }) : null,
    knopf("Schutz ausschalten", { tid: "schutz-ausschalten", class: "knopf knopf-gefahr",
      onclick: mitPasswort("/api/geheimnisse/schutz/ausschalten", "Der Schutz ist ausgeschaltet.") })];
  return abschnitt("Schutz der Geheimnisse", h("p", { tid: "schutz-status", "data-aktiv": st.aktiv ? "ja" : "nein",
    "data-gesperrt": st.gesperrt ? "ja" : "nein" }, text),
  feld("Login-Passwort", pw), h("div", { class: "knopf-leiste" }, ...knoepfe.filter(Boolean)));
}
