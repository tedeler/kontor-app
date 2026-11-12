/* Kontor – Kontoansicht (oberflaeche.md 7): Filter, Buchungsliste, Auswahl und Fokus, Mehrfachbearbeitung,
 * Inline-Bearbeitung, Kontextmenü, Drag and Drop auf Kategorien, Panels (15) und Gesten (16.4). */
import {
  BESTAND, STATUS_TEXT, abfrage, aktion, anhaengen, api, baumFolge, betragEl, betragLesen, datumEl, datumText, h, kategorien, klasse,
  kontoNach, kontoPfad, melde, neueId, oberflaeche, pfadVon, stamm, tid,
} from "./kern.js";
import {
  bestaetigen, dialog, dubletteDialog, erfassenDialog, feld, imDialog, kategorieAuswahl, kontextmenue, knopf, knopfLeiste,
  kontoEinstellungen, menuePosition, splitDialog, tagAuswahl,
} from "./ui.js";
import { kategorienBaum, langeBeruehrung, ziehbar } from "./baum.js";

const PRO_SEITE = 200;
const STATUS = ["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"];
const PARAMETER = ["von", "bis", "betrag_min", "betrag_max", "empfaenger_id", "ohne_empfaenger", "verwendungszweck",
  "suche", "kategorie_id", "unterkategorien", "unterkonten", "tag_id", "status", "sortierung"];
const SPALTEN = [["datum", "Datum", true], ["empfaenger", "Empfänger", true], ["verwendungszweck", "Verwendungszweck"],
  ["kategorie", "Kategorie"], ["tags", "Tags"], ["status", "Status"], ["betrag", "Betrag", true]];
// M11 (oberflaeche.md 22.2): Kontoansicht einer Kategorie mit zusätzlicher Spalte „Konto“ nach „Kategorie“
const SPALTEN_KATEGORIE = [...SPALTEN.slice(0, 4), ["konto", "Konto"], ...SPALTEN.slice(4)];

// ------------------------------------------------------------------ Layout der Panels (15, E-141)
const LAYOUT_SCHLUESSEL = "kontor.layout";
const VORGABE = () => ({ version: 1, panels: {
  kategorien: { bereich: "links", position: 0, breite: 240, eingeklappt: false },
  details: { bereich: "rechts", position: 1, breite: 320, eingeklappt: false } } });
const PANEL_TITEL = { kategorien: "Kategorien", details: "Einzelheiten" };
const BREITE_MIN = 160;
const BREITE_MAX = 600;

export function layoutLaden() {
  try {
    const l = JSON.parse(localStorage.getItem(LAYOUT_SCHLUESSEL));
    if (!l || l.version !== 1 || !l.panels) return VORGABE();
    for (const p of ["kategorien", "details"]) {
      const e = l.panels[p];
      if (!e || !["links", "rechts"].includes(e.bereich) || !Number.isInteger(e.position) || !Number.isInteger(e.breite)
        || e.breite < BREITE_MIN || e.breite > BREITE_MAX || typeof e.eingeklappt !== "boolean") return VORGABE();
    }
    return { version: 1, panels: { kategorien: { ...l.panels.kategorien }, details: { ...l.panels.details } } };
  } catch (e) {
    return VORGABE();
  }
}

const layoutSpeichern = (l) => {
  try { localStorage.setItem(LAYOUT_SCHLUESSEL, JSON.stringify(l)); } catch (e) { /* Speicher nicht verfügbar */ }
};

export function layoutZuruecksetzen() {
  try { localStorage.removeItem(LAYOUT_SCHLUESSEL); } catch (e) { /* Speicher nicht verfügbar */ }
}

// ------------------------------------------------------------------ Seite
export async function kontoSeite(seite, kontoId, suche) {
  const konto = await api("GET", `/api/konten/${kontoId}`);
  seite.dataset.kontoklasse = klasse(konto);   // 22.2
  const s = new Kontoansicht(seite, konto, suche);
  await s.start();
  aktiveAnsicht = s;
  return s;
}

// ------------------------------------------------------------------ Begründung „wiederkehrend“ (D-116)
let aktiveAnsicht = null;

/** Genau eine markierte Buchung der sichtbaren Kontoansicht oder null (für die Befehlspalette). */
export function markierteBuchung() {
  const s = aktiveAnsicht;
  if (!s || !s.seite || !s.seite.isConnected) return null;
  const ids = s.auswahlIds();
  return ids.length === 1 ? ids[0] : null;
}

const URTEIL_TEXT = {
  wiederkehrend: ["Ja", "Teil einer wiederkehrenden Serie"],
  zusaetzlich: ["Nein", "zusätzliche Zahlung neben einer wiederkehrenden Serie"],
  nicht_wiederkehrend: ["Nein", "nicht wiederkehrend"],
  ausgeschlossen: ["Nein", "wird bei der Erkennung nicht betrachtet"],
};
const ROLLE_TEXT = { glied: "Glied", zusaetzlich: "zusätzlich", vor_beginn: "vor Beginn", keine_serie: "–" };
const RHYTHMUS = { monatlich: "Monatlich", vierteljaehrlich: "Vierteljährlich", jaehrlich: "Jährlich" };

/** Dialog mit Urteil und Kettenprotokoll je Konto und Rhythmus. */
export async function begruendungZeigen(buchungId, ausloeser) {
  let w;
  try { w = await api("GET", `/api/buchungen/${buchungId}/wiederkehrend`); } catch (e) { return; }
  const schritt = (sc) => {
    const betroffen = sc.von.buchung_id === buchungId || (sc.vorgaenger && sc.vorgaenger.buchung_id === buchungId)
      || sc.uebersprungen.some((u) => u.buchung_id === buchungId) || (sc.fremd && sc.fremd.buchung_id === buchungId);
    return h("li", { class: `wk-schritt wk-${sc.ergebnis}${betroffen ? " wk-betroffen" : ""}`, tid: "wk-schritt",
      "data-ergebnis": sc.ergebnis, "data-grund": sc.grund || null }, sc.text);
  };
  const rhythmus = (r, offen) => h("details", { class: "wk-rhythmus", tid: `wk-rhythmus-${r.rhythmus}`, open: offen || null },
    h("summary", null, `${RHYTHMUS[r.rhythmus]}: Kette mit ${r.laenge} ${r.laenge === 1 ? "Glied" : "Gliedern"}, `
      + `mindestens ${r.mindestanzahl} nötig – ${r.erfuellt ? "erfüllt" : "nicht erfüllt"}`),
    h("ol", { class: "wk-schritte" }, r.schritte.map(schritt)));
  const eintrag = (e) => h("section", { class: "wk-eintrag", tid: "wk-eintrag", "data-urteil": e.urteil },
    h("h3", null, e.gruppe),
    h("p", { tid: "wk-eintrag-text" }, e.text),
    h("p", { class: "wk-hinweis" }, `${e.gruppe_anzahl} Buchungen in dieser Gruppe; die Kette wird ab der jüngsten `
      + `Buchung vom ${datumText(e.juengste.datum)} rückwärts gebildet. Toleranz ±5 Tage.`),
    h("details", { class: "wk-rhythmus", tid: "wk-buchungen" },
      h("summary", null, `Alle ${e.gruppe_anzahl} Buchungen der Gruppe`),
      h("table", { class: "wk-tabelle" },
        h("thead", null, h("tr", null, h("th", null, "Datum"), h("th", null, "Betrag"), h("th", null, "Rolle"))),
        h("tbody", null, e.buchungen.map((b) => h("tr", {
          class: `wk-rolle-${b.rolle}${b.buchung_id === buchungId ? " wk-betroffen" : ""}`,
          tid: "wk-buchung", "data-id": b.buchung_id, "data-rolle": b.rolle },
        h("td", null, datumText(b.datum)), betragEl("td", b.betrag),
        h("td", null, b.rolle === "glied" ? `Glied ${b.glied}` : ROLLE_TEXT[b.rolle],
          b.buchung_id === buchungId ? " (diese Buchung)" : "")))))),
    e.rhythmen.map((r, i) => rhythmus(r, i === e.rhythmen.length - 1)));
  dialog("wiederkehrend-begruendung", "Warum (nicht) wiederkehrend?", (inhalt, d) => {
    anhaengen(inhalt, [
      h("p", { class: "wk-urteil", tid: "wk-urteil", "data-urteil": w.urteil },
        h("strong", null, `Wiederkehrend? ${(URTEIL_TEXT[w.urteil] || [w.urteil])[0]}`),
        ` – ${(URTEIL_TEXT[w.urteil] || ["", ""])[1]}`),
      h("p", { class: "wk-hinweis" }, `Stand ${datumText(w.stichtag)}`),
      w.eintraege.length ? null : h("p", { tid: "wk-text" }, w.text),
      w.eintraege.map(eintrag),
      w.ausgeschlossen.map((a) => h("p", { class: "wk-hinweis", tid: "wk-ausgeschlossen" }, `${a.konto.name}: ${a.text}`)),
      knopfLeiste(knopf("Schließen", { tid: "wk-schliessen", onclick: () => d.schliessen(null) }))]);
  }, { ausloeser, klasse: "dialog-breit", schliessenKnopf: "wk-x",
    fokus: (box) => box.querySelector("[data-testid=wk-schliessen]") });
}

class Kontoansicht {
  constructor(seite, konto, suche) {
    this.seite = seite;
    this.konto = konto;
    this.istKategorie = klasse(konto) !== "bestand";   // 22.2: Kategorie oder technisches Konto
    this.spalten = this.istKategorie ? SPALTEN_KATEGORIE : SPALTEN;
    this.titel = konto.name;
    this.filter = this.filterAusUrl(suche);
    this.eintraege = [];
    this.gesamt = 0;
    this.summe = 0;
    this.seiten = 1;
    this.auswahl = new Set();
    this.anker = null;
    this.fokusId = null;
    this.zeilen = new Map();
    this.verdachte = [];
    this.layout = layoutLaden();
    this.filterSichtbar = false;   // 23.1 (E-172): jede Kontoansicht beginnt eingeklappt, nicht gespeichert
    const ziel = new URLSearchParams(suche || "").get("buchung");   // Sprungziel (D-118), kein Filter
    this.sprungId = ziel && /^\d+$/.test(ziel) ? Number(ziel) : null;
  }

  // ---------------------------------------------------------------- Filter (7.1)
  filterAusUrl(suche) {
    const q = new URLSearchParams(suche || "");
    const f = {};
    for (const p of PARAMETER) {
      if (p === "status") { const st = q.getAll("status").filter((x) => STATUS.includes(x)); if (st.length) f.status = st; }
      else if (q.has(p) && q.get(p) !== "") f[p] = q.get(p);
    }
    for (const p of ["betrag_min", "betrag_max", "empfaenger_id", "kategorie_id", "tag_id"]) {
      if (f[p] !== undefined && !/^-?\d+$/.test(f[p])) delete f[p];
    }
    if (f.ohne_empfaenger !== undefined && f.ohne_empfaenger !== "true") delete f.ohne_empfaenger;
    for (const p of ["unterkategorien", "unterkonten"]) if (f[p] !== undefined && f[p] !== "true") delete f[p];
    if (this.istKategorie) delete f.unterkategorien;   // 22.2: entfällt in der Kategorieansicht
    return f;
  }

  get sortierung() { return this.filter.sortierung || "-datum"; }

  filterAnzahl() {
    return Object.keys(this.filter).filter((k) => k !== "sortierung").length;
  }

  urlSchreiben() {
    const f = { ...this.filter };   // nur gesetzte Filter und eine gewählte Sortierung (7.1)
    history.replaceState(history.state, "", `/konten/${this.konto.id}${abfrage(f)}`);
    if (oberflaeche.urlGeaendert) oberflaeche.urlGeaendert();   // Tab merkt sich Filter und Sortierung
  }

  async filterSetzen(name, wert) {
    const neu = { ...this.filter };
    if (wert === null || wert === undefined || wert === "" || (Array.isArray(wert) && !wert.length)) delete neu[name];
    else neu[name] = wert;
    if (JSON.stringify(neu) === JSON.stringify(this.filter)) return;
    this.filter = neu;
    this.auswahl.clear();           // ein Filterwechsel hebt die Auswahl auf (7.1)
    this.anker = null;
    this.seiten = 1;
    this.urlSchreiben();
    await this.laden();
  }

  // ---------------------------------------------------------------- Laden
  async start() {
    this.aufbauen();
    await this.laden();
    if (this.sprungId !== null) await this.springen(this.sprungId);
  }

  /** Markiert eine Buchung und rollt zu ihr; lädt dafür bei Bedarf weitere Seiten nach (D-118). */
  async springen(id) {
    this.sprungId = null;
    while (!this.zeilen.has(id) && this.eintraege.length < this.gesamt) {
      this.seiten += 1;
      await this.laden();
    }
    this.urlSchreiben();   // Sprungziel aus der Adresse entfernen
    if (!this.zeilen.has(id)) { melde("hinweis", "Die Buchung ist mit den aktuellen Filtern nicht sichtbar."); return; }
    this.sprungMarkieren(id);
  }

  async laden() {
    const nr = (this.ladeNr = (this.ladeNr || 0) + 1);   // nur die jüngste Antwort zählt
    this.seite.dataset.geladen = "nein";
    const basis = { konto_id: this.konto.id, ...this.filter, sortierung: this.sortierung, pro_seite: PRO_SEITE };
    const eintraege = [];
    let gesamt = 0;
    let summe = 0;
    for (let n = 1; n <= this.seiten; n++) {
      const s = await api("GET", "/api/buchungen" + abfrage({ ...basis, seite: n }));
      eintraege.push(...s.eintraege);
      gesamt = s.gesamt;
      summe = s.summe;
      if (eintraege.length >= gesamt) break;
    }
    let verdachte = [];
    try { verdachte = await api("GET", "/api/dubletten?status=offen"); } catch (e) { verdachte = []; }
    await this.regelnLaden(eintraege);
    if (nr !== this.ladeNr) return;
    this.kandidatenCache = new Map();
    this.verdachte = verdachte;
    this.eintraege = eintraege;
    this.gesamt = gesamt;
    this.summe = summe;
    const ids = new Set(eintraege.map((b) => b.id));
    for (const id of [...this.auswahl]) if (!ids.has(id)) this.auswahl.delete(id);
    if (!ids.has(this.anker)) this.anker = null;
    if (!ids.has(this.fokusId)) this.fokusId = null;
    this.listeZeichnen();
    this.seite.dataset.geladen = "ja";
  }

  async aktualisieren() {
    await this.laden();
    this.baumNeu();       // Kategorien können sich geändert haben (Umbenennen, Verschieben, Anlegen, Löschen)
  }

  // ---------------------------------------------------------------- Aufbau
  aufbauen() {
    const s = this.seite;
    const mobil = oberflaeche.istMobil();
    this.filterKnopf = h("button", { type: "button", class: "knopf", tid: "filter-umschalten",
      "aria-controls": "filter-leiste", "aria-expanded": String(this.filterSichtbar),
      onclick: () => this.filterUmschalten() }, "Filter ",
    this.filterZahl = h("span", { class: "zahl-marke sichtbar", tid: "filter-anzahl", "data-anzahl": "0" }, "0"));
    this.anzahlEl = h("span", { tid: "buchungsliste-anzahl", "data-anzahl": "0" });
    this.summeEl = h("span", { tid: "buchungsliste-summe", "data-betrag": "0", class: "betrag" });
    this.auswahlEl = h("span", { tid: "auswahl-anzahl", "data-anzahl": "0", class: "auswahl-anzahl" });
    const erfassen = knopf("Buchung erfassen", { tid: "buchung-erfassen",
      onclick: (e) => erfassenDialog(this.konto.id, e.currentTarget) });
    s.append(h("div", { class: "seiten-kopf" }, h("h1", null, this.konto.name),
      h("div", { class: "werkzeuge" }, this.filterKnopf, erfassen,
        knopf("Einstellungen…", { tid: "konto-einstellungen-oeffnen", onclick: (e) => kontoEinstellungen(this.konto, e.currentTarget) }),
        this.istKategorie ? null : knopf("Verschieben…", { tid: "konto-verschieben",
          title: "Buchungen dieses Kontos auf ein anderes Konto verschieben",
          onclick: (e) => this.verschiebenDialog(this.auswahlIds(), e.currentTarget) }))),
    h("div", { class: "listen-info" }, this.anzahlEl, " · Summe ", this.summeEl, " · ", this.auswahlEl));
    this.filterLeiste = this.filterAufbauen();
    s.append(this.filterLeiste);
    this.liste = h("div", { role: "grid", tid: "buchungsliste", "aria-multiselectable": "true", "aria-label": "Buchungen",
      "aria-rowcount": "-1", class: "buchungsliste" + (this.istKategorie ? " mit-konto" : ""),
      "data-kompakt": mobil ? "ja" : "nein" });
    this.leerEl = h("p", { tid: "buchungsliste-leer", class: "leer", hidden: true }, "Keine Buchungen.");
    this.mehrEl = knopf("Weitere laden", { tid: "buchungsliste-mehr", hidden: true, onclick: async () => {
      this.seiten += 1;
      await this.laden();
    } });
    this.listenSpalte = h("div", { class: "listen-spalte" }, this.liste, this.leerEl, this.mehrEl);
    this.arbeit = h("div", { class: "arbeitsbereich" });
    s.append(this.arbeit);
    this.mehrfach = this.mehrfachAufbauen();
    s.append(this.mehrfach);
    this.arbeitZeichnen();
    this.listeEreignisse();
  }

  layoutGeaendert() {
    const mobil = oberflaeche.istMobil();
    this.liste.dataset.kompakt = mobil ? "ja" : "nein";
    this.arbeitZeichnen();
    this.listeZeichnen();
  }

  /** Tab über Navigation oder Link erneut angefordert: Filterleiste eingeklappt (23.1, E-172), Rest bleibt (D-119). */
  wiederAngefordert() {
    if (this.filterSichtbar) this.filterUmschalten();
  }

  filterUmschalten() {
    this.filterSichtbar = !this.filterSichtbar;
    this.filterLeiste.hidden = !this.filterSichtbar;
    this.filterKnopf.setAttribute("aria-expanded", String(this.filterSichtbar));
  }

  filterAufbauen() {
    const f = this.filter;
    const leiste = h("div", { class: "filter-leiste", id: "filter-leiste", tid: "filter-leiste", role: "search",
      "aria-label": "Filter der Buchungsliste", hidden: !this.filterSichtbar });
    const feld = (text, el) => {
      el.id = el.id || neueId("filter");
      return h("div", { class: "feld" }, h("label", { for: el.id }, text), el);
    };
    const datum = (name) => {
      const el = h("input", { type: "date", tid: `filter-${name}`, value: f[name] || "" });
      el.addEventListener("change", () => this.filterSetzen(name, el.value));
      return el;
    };
    const text = (name, testid) => {
      const el = h("input", { type: "text", tid: testid, value: f[name] || "", maxlength: "200" });
      const setzen = () => this.filterSetzen(name, el.value.trim());
      el.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); setzen(); } });
      el.addEventListener("change", setzen);
      return el;
    };
    const betrag = (name, testid) => {
      const el = h("input", { type: "text", inputmode: "decimal", tid: testid,
        value: f[name] !== undefined ? betragEingabeText(Number(f[name])) : "" });
      const setzen = () => {
        const c = betragLesen(el.value);
        if (c === null) { el.setAttribute("aria-invalid", "true"); return; }
        el.removeAttribute("aria-invalid");
        this.filterSetzen(name, c === "" ? "" : String(c));
      };
      el.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); setzen(); } });
      el.addEventListener("change", setzen);
      return el;
    };
    const empf = h("select", { tid: "filter-empfaenger" }, h("option", { value: "" }, "– alle Empfänger –"),
      h("option", { value: "ohne" }, "ohne Empfänger"),
      stamm.empfaenger.map((e) => h("option", { value: String(e.id) }, e.name)));
    empf.value = f.ohne_empfaenger ? "ohne" : (f.empfaenger_id || "");
    empf.addEventListener("change", async () => {
      const neu = { ...this.filter };
      delete neu.empfaenger_id;
      delete neu.ohne_empfaenger;
      if (empf.value === "ohne") neu.ohne_empfaenger = "true";
      else if (empf.value) neu.empfaenger_id = empf.value;
      this.filter = neu;
      this.auswahl.clear();
      this.anker = null;
      this.seiten = 1;
      this.urlSchreiben();
      await this.laden();
    });
    // 22.2: In einer Kategorie filtert `filter-konto` über die Bestandskonten (REST kategorie_id).
    const katListe = this.istKategorie
      ? baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art)))
      : kategorien();
    const kat = h("select", { tid: this.istKategorie ? "filter-konto" : "filter-kategorie" },
      h("option", { value: "" }, this.istKategorie ? "– alle Konten –" : "– alle Kategorien –"),
      katListe.map(({ konto }) => h("option", { value: String(konto.id) }, kontoPfad(konto))));
    kat.value = f.kategorie_id || "";
    kat.addEventListener("change", () => this.filterSetzen("kategorie_id", kat.value));
    const unter = h("input", { type: "checkbox", tid: "filter-unterkategorien", checked: f.unterkategorien === "true" });
    unter.addEventListener("change", () => this.filterSetzen("unterkategorien", unter.checked ? "true" : ""));
    const unterkonten = h("input", { type: "checkbox", tid: "filter-unterkonten", checked: f.unterkonten === "true" });
    unterkonten.addEventListener("change", () => this.filterSetzen("unterkonten", unterkonten.checked ? "true" : ""));
    const tag = h("select", { tid: "filter-tag" }, h("option", { value: "" }, "– alle Tags –"),
      stamm.tags.slice().sort((a, b) => a.name.localeCompare(b.name, "de"))
        .map((t) => h("option", { value: String(t.id) }, t.name)));
    tag.value = f.tag_id || "";
    tag.addEventListener("change", () => this.filterSetzen("tag_id", tag.value));
    const status = h("fieldset", { class: "status-filter" }, h("legend", null, "Status"),
      STATUS.map((st) => {
        const c = h("input", { type: "checkbox", tid: `filter-status-${st}`, value: st,
          checked: (f.status || []).includes(st) });
        c.addEventListener("change", () => {
          const gew = [...leiste.querySelectorAll(".status-filter input:checked")].map((x) => x.value);
          this.filterSetzen("status", gew);
        });
        return h("label", { class: "wahl" }, c, " " + STATUS_TEXT[st]);
      }));
    const zurueck = knopf("Filter zurücksetzen", { tid: "filter-zuruecksetzen", onclick: async () => {
      const sort = this.filter.sortierung;
      this.filter = sort ? { sortierung: sort } : {};
      this.auswahl.clear();
      this.anker = null;
      this.seiten = 1;
      this.urlSchreiben();
      const neu = this.filterAufbauen();
      neu.hidden = this.filterLeiste.hidden;
      this.filterLeiste.replaceWith(neu);
      this.filterLeiste = neu;
      await this.laden();
    } });
    leiste.append(...[feld("Von", datum("von")), feld("Bis", datum("bis")),
      feld("Betrag ab (€)", betrag("betrag_min", "filter-betrag-min")),
      feld("Betrag bis (€)", betrag("betrag_max", "filter-betrag-max")),
      feld("Empfänger", empf), feld("Verwendungszweck", text("verwendungszweck", "filter-verwendungszweck")),
      feld("Freitext", text("suche", "filter-freitext")), feld(this.istKategorie ? "Konto" : "Kategorie", kat),
      this.istKategorie ? null : h("label", { class: "wahl" }, unter, " mit Unterkategorien"),
      h("label", { class: "wahl" }, unterkonten, " mit Unterkonten"), feld("Tag", tag), status, zurueck].filter(Boolean));
    return leiste;
  }

  // ---------------------------------------------------------------- Panels (15)
  arbeitZeichnen() {
    const mobil = oberflaeche.istMobil();
    this.panelEls = {};
    if (mobil) {
      this.arbeit.replaceChildren(this.listenSpalte);
      this.baumEl = null;
      return;
    }
    const bereich = (name) => {
      const el = h("div", { class: `bereich bereich-${name}`, tid: `bereich-${name}` });
      const panels = Object.entries(this.layout.panels).filter(([, p]) => p.bereich === name)
        .sort((a, b) => a[1].position - b[1].position);
      // von außen (Fensterrand) nach innen (Liste): links aufsteigend, rechts absteigend in der DOM-Reihenfolge
      if (name === "rechts") panels.reverse();
      for (const [p] of panels) el.append(this.panel(p));
      el.append(h("div", { class: "ablage", tid: `ablage-${name}`, hidden: true, "aria-hidden": "true" }));
      return el;
    };
    this.bereichLinks = bereich("links");
    this.bereichRechts = bereich("rechts");
    this.arbeit.replaceChildren(this.bereichLinks, this.listenSpalte, this.bereichRechts);
    this.detailsZeichnen();
  }

  panel(p) {
    const l = this.layout.panels[p];
    const kopfId = neueId("panel-titel");
    const einklappen = h("button", { type: "button", class: "knopf-flach", tid: `panel-einklappen-${p}`,
      "aria-expanded": String(!l.eingeklappt), "aria-label": `Panel ${PANEL_TITEL[p]} ${l.eingeklappt ? "aufklappen" : "einklappen"}`,
      onclick: () => { l.eingeklappt = !l.eingeklappt; this.layoutAnwenden(); } }, l.eingeklappt ? "▸" : "▾");
    const verschieben = h("button", { type: "button", class: "knopf-flach", tid: `panel-verschieben-${p}`,
      "aria-label": `Panel ${PANEL_TITEL[p]} in den ${l.bereich === "links" ? "rechten" : "linken"} Bereich verschieben`,
      onclick: () => this.panelVerschieben(p, l.bereich === "links" ? "rechts" : "links") }, "⇄");
    const kopf = h("div", { class: "panel-kopf", tid: `panel-kopf-${p}` }, h("h2", { id: kopfId }, PANEL_TITEL[p]),
      verschieben, einklappen);
    const inhalt = h("div", { class: "panel-inhalt" });
    const griff = h("div", { class: "panel-griff", tid: `panel-groesse-${p}`, role: "separator",
      "aria-orientation": "vertical", "aria-valuenow": String(l.breite), "aria-valuemin": String(BREITE_MIN),
      "aria-valuemax": String(BREITE_MAX), tabindex: "0", "aria-label": `Breite des Panels ${PANEL_TITEL[p]}` });
    const el = h("section", { class: "panel", tid: `panel-${p}`, "aria-labelledby": kopfId, "data-bereich": l.bereich,
      "data-eingeklappt": l.eingeklappt ? "ja" : "nein" }, kopf, inhalt, griff);
    el.style.width = (l.eingeklappt ? 40 : l.breite) + "px";
    this.panelEls[p] = { el, inhalt, griff };
    this.griffBedienung(p, griff);
    this.panelZiehen(p, kopf);
    if (p === "kategorien") {
      this.baumEl = kategorienBaum({ neuZeichnen: () => this.baumNeu() });
      inhalt.append(this.baumEl);
    }
    return el;
  }

  baumNeu() {
    const pe = this.panelEls.kategorien;
    if (!pe) return;
    this.baumEl = kategorienBaum({ neuZeichnen: () => this.baumNeu() });
    pe.inhalt.replaceChildren(this.baumEl);
  }

  layoutAnwenden() {
    layoutSpeichern(this.layout);
    this.arbeitZeichnen();
  }

  panelVerschieben(p, ziel) {
    const andere = Object.values(this.layout.panels).filter((x) => x.bereich === ziel);
    const l = this.layout.panels[p];
    l.bereich = ziel;
    l.position = andere.length ? Math.max(...andere.map((x) => x.position)) + 1 : 0;   // innerste Stelle (15.2)
    this.layoutAnwenden();
  }

  breiteSetzen(p, breite) {
    const l = this.layout.panels[p];
    l.breite = Math.max(BREITE_MIN, Math.min(BREITE_MAX, Math.round(breite)));
    const pe = this.panelEls[p];
    if (pe) {
      pe.griff.setAttribute("aria-valuenow", String(l.breite));
      if (!l.eingeklappt) pe.el.style.width = l.breite + "px";
    }
    layoutSpeichern(this.layout);
  }

  griffBedienung(p, griff) {
    const l = this.layout.panels[p];
    griff.addEventListener("keydown", (e) => {
      const links = l.bereich === "links";
      const schritt = { ArrowRight: links ? 16 : -16, ArrowLeft: links ? -16 : 16 }[e.key];
      if (schritt) { e.preventDefault(); this.breiteSetzen(p, l.breite + schritt); }
      else if (e.key === "Home") { e.preventDefault(); this.breiteSetzen(p, BREITE_MIN); }
      else if (e.key === "End") { e.preventDefault(); this.breiteSetzen(p, BREITE_MAX); }
    });
    griff.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      const x0 = e.clientX;
      const b0 = l.breite;
      griff.setPointerCapture(e.pointerId);
      const bewegen = (ev) => {
        const dx = ev.clientX - x0;
        this.breiteSetzen(p, l.bereich === "links" ? b0 + dx : b0 - dx);
      };
      const ende = () => {
        griff.removeEventListener("pointermove", bewegen);
        griff.removeEventListener("pointerup", ende);
        griff.removeEventListener("pointercancel", ende);
      };
      griff.addEventListener("pointermove", bewegen);
      griff.addEventListener("pointerup", ende);
      griff.addEventListener("pointercancel", ende);
    });
  }

  panelZiehen(p, kopf) {
    let zielBereich = null;
    ziehbar(kopf, {
      quelle: () => ({ p }),
      text: () => PANEL_TITEL[p],
      start: () => {
        this.arbeit.classList.add("panel-ziehen");
        for (const n of ["links", "rechts"]) tid(`ablage-${n}`, this.arbeit).hidden = false;
      },
      ziel: (x, y) => {
        zielBereich = null;
        for (const n of ["links", "rechts"]) {
          const a = tid(`ablage-${n}`, this.arbeit);
          const r = a && a.getBoundingClientRect();
          if (r && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
            zielBereich = n;
            return { el: a, annehmen: true, bereich: n };
          }
        }
        return null;
      },
      ende: () => {
        this.arbeit.classList.remove("panel-ziehen");
        for (const n of ["links", "rechts"]) { const a = tid(`ablage-${n}`, this.arbeit); if (a) a.hidden = true; }
      },
      ablegen: (q, z) => {
        if (z.bereich !== this.layout.panels[p].bereich) this.panelVerschieben(p, z.bereich);
      },
    });
    return zielBereich;
  }

  // ---------------------------------------------------------------- Einzelheiten (7.3)
  // ---------------------------------------------------------------- Vorschläge (D-112)
  vorschlagText(v) {
    const pct = v.sicherheit === null || v.sicherheit === undefined ? null : `${Math.floor((v.sicherheit + 5) / 10)} %`;
    if (v.quelle === "lernmodell") {
      return { marke: pct || "LM", lang: `Vorschlag des Lernmodells${pct ? `, Sicherheit ${pct}` : ""}` };
    }
    if (v.quelle === "regel") {
      const name = v.regel_id && this.regelNamen ? this.regelNamen.get(v.regel_id) : null;
      return { marke: "Regel", lang: name ? `Vorschlag der Regel „${name}“` : "Vorschlag einer Regel" };
    }
    return { marke: "Empf.", lang: "Vorschlag: Standardkategorie des Empfängers" };
  }

  async regelnLaden(eintraege) {
    if (!eintraege.some((b) => b.vorschlag && b.vorschlag.quelle === "regel")) return;
    try {
      const regeln = await api("GET", "/api/regeln");
      this.regelNamen = new Map(regeln.map((r) => [r.id, r.name]));
    } catch (e) { /* ohne Regelnamen */ }
  }

  vorschlagDetails(b) {
    const v = b.vorschlag;
    const vs = this.vorschlagText(v);
    const kandidaten = h("ol", { class: "vorschlag-kandidaten", tid: "details-vorschlag-kandidaten" });
    const el = h("div", { class: "details-vorschlag", tid: "details-vorschlag", "data-quelle": v.quelle },
      h("p", null, h("strong", null, "Vorschlag: "), pfadVon(v.kategorie_id)),
      h("p", { class: "klein" }, vs.lang, v.vorher_konto_id ? ` · vorher: ${pfadVon(v.vorher_konto_id)}` : ""),
      kandidaten,
      knopfLeiste(knopf("Annehmen", { tid: "details-vorschlag-annehmen", onclick: () => this.vorschlag(null, [b.id], "annehmen") }),
        knopf("Ablehnen", { tid: "details-vorschlag-ablehnen", onclick: () => this.vorschlag(null, [b.id], "ablehnen") })));
    // Alternativen des Lernmodells (lernmodell.md 5.3, ohne Wirkung)
    this.kandidatenCache = this.kandidatenCache || new Map();
    const fuellen = (alle) => {
      const liste = (alle || []).filter((k) => k.sicherheit >= 5 || k.kategorie_id === v.kategorie_id);   // ab 1 %
      if (!liste.length) return;
      kandidaten.replaceChildren(h("li", { class: "klein kopf" }, "Einschätzung des Lernmodells:"),
        ...liste.map((k) => h("li", { "data-kategorie-id": String(k.kategorie_id),
          class: k.kategorie_id === v.kategorie_id ? "gewaehlt" : "" },
        `${pfadVon(k.kategorie_id)} – ${Math.floor((k.sicherheit + 5) / 10)} %`,
        k.kategorie_id !== v.kategorie_id ? knopf("Übernehmen", { class: "knopf knopf-klein",
          tid: `details-kandidat-${k.kategorie_id}`, onclick: () => this.kategorieSetzen([b.id], k.kategorie_id) }) : null)));
    };
    if (this.kandidatenCache.has(b.id)) fuellen(this.kandidatenCache.get(b.id));
    else {
      api("POST", "/api/lernmodell/vorhersage", { eintraege: [{ buchung_id: b.id }] }).then((r) => {
        const liste = (r.ergebnisse[0] || {}).kandidaten || [];
        this.kandidatenCache.set(b.id, liste);
        fuellen(liste);
      }).catch(() => { /* ohne Alternativen */ });
    }
    return el;
  }

  detailsInhalt(b) {
    if (!b) return [h("p", { class: "leer" }, "Keine Buchung gewählt.")];
    return [
      b.vorschlag ? this.vorschlagDetails(b) : null,
      h("p", null, datumText(b.datum), " · ", b.empfaenger ? b.empfaenger.name : "ohne Empfänger"),
      h("p", { class: "zweck" }, b.verwendungszweck),
      h("ul", { class: "details-splits" }, b.splits.map((s) => h("li", { tid: `details-split-${s.id}`, class: "details-split" },
        h("span", null, pfadVon(s.konto_id)), " ", betragEl("span", s.betrag), s.memo ? h("small", null, " " + s.memo) : null))),
      b.tags.length ? h("p", null, "Tags: ", b.tags.map((t) => t.name).join(", ")) : null,
      b.extern_ids.length ? h("p", { class: "klein" }, "Herkunft: ", b.extern_ids.join(", ")) : null,
      h("p", { class: "klein" }, "Status: ", STATUS_TEXT[b.status] || b.status, b.abgestimmt ? " · abgestimmt" : ""),
    ];
  }

  detailsZeichnen() {
    const pe = this.panelEls && this.panelEls.details;
    if (!pe) return;
    const b = this.eintraege.find((x) => x.id === this.fokusId);
    pe.inhalt.replaceChildren(...this.detailsInhalt(b).filter(Boolean));
  }

  detailsOeffnen() {
    if (oberflaeche.istMobil()) {
      const b = this.eintraege.find((x) => x.id === this.fokusId);
      if (!b) return;
      dialog("panel-details", "Einzelheiten", (inhalt) => {
        inhalt.append(...this.detailsInhalt(b).filter(Boolean));
      }, { schliessenKnopf: "details-schliessen", klasse: "dialog-details", fokus: (box) => tid("details-schliessen", box) });
      return;
    }
    const l = this.layout.panels.details;
    if (l.eingeklappt) { l.eingeklappt = false; this.layoutAnwenden(); }
    this.detailsZeichnen();
  }

  // ---------------------------------------------------------------- Liste (7.2)
  listeZeichnen() {
    const kompakt = oberflaeche.istMobil();
    const sort = this.sortierung;
    const kopf = h("div", { role: "row", class: "liste-kopf" }, this.spalten.map(([feld, text, sortierbar]) => {
      const aktiv = sort.replace(/^-/, "") === feld;
      const zelle = h("div", { role: "columnheader", class: `zelle zelle-${feld}`, "data-feld": feld,
        "aria-sort": sortierbar ? (aktiv ? (sort.startsWith("-") ? "descending" : "ascending") : "none") : null });
      if (sortierbar) {
        zelle.append(h("button", { type: "button", class: "spalten-knopf", tid: `spalte-${feld}`,
          onclick: () => this.filterSetzen("sortierung", aktiv ? (sort.startsWith("-") ? feld : "-" + feld) : feld) },
        text, aktiv ? (sort.startsWith("-") ? " ↓" : " ↑") : ""));
      } else zelle.append(text);
      return zelle;
    }));
    this.zeilen = new Map();
    const fokusImGrid = this.liste.contains(document.activeElement) && document.activeElement.getAttribute("role") === "row";
    const editor = this.editorOffen;
    const editorFokus = editor ? editor.loesen() : false;
    const zeilen = this.eintraege.map((b) => this.zeile(b, kompakt));
    this.liste.replaceChildren(kopf, ...zeilen);
    if (editor && this.editorOffen === editor) editor.umziehen(editorFokus);
    this.anzahlEl.dataset.anzahl = String(this.gesamt);
    this.anzahlEl.textContent = this.gesamt === 1 ? "1 Buchung" : `${this.gesamt} Buchungen`;
    this.summeEl.dataset.betrag = String(this.summe);
    this.summeEl.textContent = betragEl("span", this.summe).textContent;
    this.leerEl.hidden = this.gesamt !== 0;
    this.mehrEl.hidden = this.eintraege.length >= this.gesamt;
    this.filterZahl.dataset.anzahl = String(this.filterAnzahl());
    this.filterZahl.textContent = String(this.filterAnzahl());
    this.auswahlZeigen();
    if (fokusImGrid && this.fokusId) this.zeilen.get(this.fokusId)?.focus({ preventScroll: true });
    this.detailsZeichnen();
  }

  zeile(b, kompakt) {
    const gegen = gegensplits(b);
    // oberflaeche.md 7.2: Pfad; ohne kategorie_id „Gesplittet“, „Umbuchung“ oder der Pfad des einen Gegensplits
    const katText = b.kategorie_id ? pfadVon(b.kategorie_id)
      : (gegen.length > 1 ? "Gesplittet" : gegen.length === 0 ? "Umbuchung" : pfadVon(gegen[0].konto_id));
    const vs = b.vorschlag ? this.vorschlagText(b.vorschlag) : null;
    const kat = h("div", { role: "gridcell", class: "zelle zelle-kategorie", "data-feld": "kategorie",
      "data-kategorie-id": b.kategorie_id ? String(b.kategorie_id) : "" },
    h("span", { class: "kat-text" + (vs ? " vorschlag-kategorie" : ""), title: vs ? `${katText} – ${vs.lang}` : katText }, katText));
    if (b.vorschlag) {
      // Sammelpaket (D-112): vorgeschlagene Kategorie, Quelle und Sicherheit je Zeile
      kat.append(h("span", { class: "vorschlag-marke", tid: "vorschlag-marke", title: vs.lang, "aria-label": vs.lang,
        "data-quelle": b.vorschlag.quelle, "data-sicherheit": b.vorschlag.sicherheit === null || b.vorschlag.sicherheit === undefined
          ? "" : String(b.vorschlag.sicherheit) }, vs.marke), h("span", { class: "vorschlag-knoepfe" },
        h("button", { type: "button", class: "mini-knopf", tid: `vorschlag-annehmen-${b.id}`, "data-nicht-ziehen": "",
          "aria-label": `Vorschlag ${katText} annehmen`, onclick: (e) => this.vorschlag(e, [b.id], "annehmen") }, "✓"),
        h("button", { type: "button", class: "mini-knopf", tid: `vorschlag-ablehnen-${b.id}`, "data-nicht-ziehen": "",
          "aria-label": "Vorschlag ablehnen", onclick: (e) => this.vorschlag(e, [b.id], "ablehnen") }, "✗")));
    }
    const empfName = b.empfaenger ? b.empfaenger.name : "";
    const empf = h("div", { role: "gridcell", class: "zelle zelle-empfaenger", "data-feld": "empfaenger",
      "data-empfaenger-id": b.empfaenger ? String(b.empfaenger.id) : "" },
    empfName || (kompakt ? h("span", { class: "ersatz" }, b.verwendungszweck) : ""));
    const zeile = h("div", { role: "row", tid: `buchung-${b.id}`, class: "zeile", "aria-selected": "false",
      tabindex: "-1", "data-id": String(b.id), "data-status": b.status, "data-vorschlag": b.vorschlag ? "ja" : "nein" },
    datumEl("div", b.datum, { role: "gridcell", class: "zelle zelle-datum", "data-feld": "datum" }),
    empf,
    h("div", { role: "gridcell", class: "zelle zelle-verwendungszweck", "data-feld": "verwendungszweck" }, b.verwendungszweck),
    kat,
    this.istKategorie ? kontoZelle(b) : null,
    h("div", { role: "gridcell", class: "zelle zelle-tags", "data-feld": "tags" },
      b.tags.map((t) => h("span", { class: "tag", tid: "tag", "data-tag-id": String(t.id) }, t.name))),
    h("div", { role: "gridcell", class: "zelle zelle-status", "data-feld": "status" }, STATUS_TEXT[b.status] || b.status),
    betragEl("div", b.betrag, { role: "gridcell", class: "zelle zelle-betrag", "data-feld": "betrag" }));
    if (b.abgestimmt || b.status === "abgeglichen") zeile.dataset.gesperrt = "ja";
    this.zeilen.set(b.id, zeile);
    return zeile;
  }

  auswahlZeigen() {
    for (const [id, z] of this.zeilen) {
      z.setAttribute("aria-selected", this.auswahl.has(id) ? "true" : "false");
      z.tabIndex = id === this.fokusId ? 0 : -1;
    }
    if (!this.fokusId && this.zeilen.size) [...this.zeilen.values()][0].tabIndex = 0;
    const n = this.auswahl.size;
    this.auswahlEl.dataset.anzahl = String(n);
    this.auswahlEl.textContent = n ? `${n} ausgewählt` : "keine Auswahl";
    this.mehrfach.hidden = n === 0;
    const mitVorschlag = this.eintraege.some((b) => this.auswahl.has(b.id) && b.vorschlag);
    for (const t of ["mehrfach-vorschlag-annehmen", "mehrfach-vorschlag-ablehnen"]) tid(t, this.mehrfach).disabled = !mitVorschlag;
  }

  ids() { return this.eintraege.map((b) => b.id); }

  bereich(a, b) {
    const ids = this.ids();
    let i = ids.indexOf(a);
    let j = ids.indexOf(b);
    if (i < 0) i = j;
    if (i > j) [i, j] = [j, i];
    return ids.slice(i, j + 1);
  }

  fokussieren(id, mitDom = true) {
    this.fokusId = id;
    this.auswahlZeigen();
    const z = this.zeilen.get(id);
    if (z && mitDom) {
      // nur senkrecht nachführen: eine Zeile ist breiter als die Liste, waagerecht bleibt die Lage (23.2)
      const links = this.listenSpalte ? this.listenSpalte.scrollLeft : 0;
      z.focus({ preventScroll: true });
      z.scrollIntoView({ block: "nearest" });
      if (this.listenSpalte) this.listenSpalte.scrollLeft = links;
    }
    this.detailsZeichnen();
  }

  klick(id, e) {
    const strg = e.ctrlKey || e.metaKey;
    if (oberflaeche.istMobil() && !strg && !e.shiftKey) {
      if (this.auswahl.size === 0) { this.fokussieren(id); this.detailsOeffnen(); return; }
      if (this.auswahl.has(id)) this.auswahl.delete(id); else this.auswahl.add(id);
      this.anker = id;
      this.fokussieren(id);
      return;
    }
    if (strg && e.shiftKey) {
      if (this.anker !== null) for (const x of this.bereich(this.anker, id)) this.auswahl.add(x);
      else { this.auswahl.add(id); this.anker = id; }
    } else if (strg) {
      if (this.auswahl.has(id)) this.auswahl.delete(id); else this.auswahl.add(id);
      this.anker = id;
    } else if (e.shiftKey && this.anker !== null) {
      this.auswahl = new Set(this.bereich(this.anker, id));
    } else {
      this.auswahl = new Set([id]);
      this.anker = id;
    }
    this.fokussieren(id);
  }

  taste(e) {
    const z = e.target.closest('[role="row"][data-id]');
    if (!z || e.target !== z) return;
    const id = Number(z.dataset.id);
    const ids = this.ids();
    const i = ids.indexOf(id);
    const strg = e.ctrlKey || e.metaKey;
    const ziel = { ArrowDown: ids[i + 1], ArrowUp: ids[i - 1], Home: ids[0], End: ids[ids.length - 1] }[e.key];
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
      e.preventDefault();
      if (ziel === undefined) return;
      if (strg && !e.shiftKey) { this.fokussieren(ziel); return; }
      if (e.shiftKey) {
        if (this.anker === null) this.anker = id;
        this.auswahl = new Set(this.bereich(this.anker, ziel));
      } else {
        this.auswahl = new Set([ziel]);
        this.anker = ziel;
      }
      this.fokussieren(ziel);
    } else if (e.key === " ") {
      e.preventDefault();
      if (this.auswahl.has(id)) this.auswahl.delete(id); else this.auswahl.add(id);
      this.anker = id;
      this.fokussieren(id);
    } else if (strg && (e.key === "a" || e.key === "A")) {
      e.preventDefault();
      this.auswahl = new Set(ids);
      this.auswahlZeigen();
    } else if (e.key === "F2") {
      e.preventDefault();
      this.bearbeiten(id, "verwendungszweck");
    } else if (e.key === "Delete") {
      e.preventDefault();
      if (!this.auswahl.size) { this.auswahl.add(id); this.auswahlZeigen(); }
      this.loeschen(z);
    } else if (e.key === "Enter") {
      e.preventDefault();
      this.fokussieren(id);
      this.detailsOeffnen();
    } else if ((e.key === "F10" && e.shiftKey) || e.key === "ContextMenu") {
      e.preventDefault();
      if (!this.auswahl.has(id)) { this.auswahl = new Set([id]); this.anker = id; }
      this.fokussieren(id);
      const [x, y] = menuePosition(null, z);
      this.menue(x, y, z, e.altKey);
    }
  }

  escape() {
    if (!this.auswahl.size) return false;
    this.auswahl.clear();
    this.auswahlZeigen();
    return true;
  }

  // ---------------------------------------------------------------- Ereignisse der Liste
  listeEreignisse() {
    const zeileVon = (t) => t && t.closest && t.closest('[role="row"][data-id]');
    this.liste.addEventListener("click", (e) => {
      if (e.target.closest("button, input, select, [data-testid=inline-editor]")) return;
      const z = zeileVon(e.target);
      if (z) this.klick(Number(z.dataset.id), e);
    });
    this.liste.addEventListener("dblclick", (e) => {
      if (oberflaeche.istMobil()) return;
      const zelle = e.target.closest("[data-feld]");
      const z = zeileVon(e.target);
      if (!z || !zelle || e.target.closest("button, input, select")) return;
      if (["datum", "verwendungszweck", "kategorie", "empfaenger", "status", "betrag"].includes(zelle.dataset.feld)) {
        this.bearbeiten(Number(z.dataset.id), zelle.dataset.feld);
      }
    });
    this.liste.addEventListener("keydown", (e) => this.taste(e));
    this.liste.addEventListener("contextmenu", (e) => {
      const z = zeileVon(e.target);
      if (!z || e.target.closest("input, textarea")) return;
      e.preventDefault();
      const id = Number(z.dataset.id);
      if (!this.auswahl.has(id)) { this.auswahl = new Set([id]); this.anker = id; }
      this.fokussieren(id);
      this.menue(e.clientX, e.clientY, z, e.altKey);
    });
    // Drag and Drop auf eine Kategorie im Panel (10)
    ziehbar(this.liste, {
      quelle: (ev) => {
        const z = zeileVon(ev.target);
        return z && !ev.target.closest("[data-testid=inline-editor]") ? { id: Number(z.dataset.id), z } : null;
      },
      start: (q) => {
        if (!this.auswahl.has(q.id)) { this.auswahl = new Set([q.id]); this.anker = q.id; this.fokussieren(q.id); }
        q.ids = this.ids().filter((x) => this.auswahl.has(x));
      },
      text: (q) => (this.auswahl.size > 1 ? `${this.auswahl.size} Buchungen` : "1 Buchung"),
      ziel: (x, y) => (this.baumEl ? this.baumEl.buchungsZiel(x, y) : null),
      ablegen: (q, z) => this.kategorieSetzen(q.ids, z.kategorie_id),
    });
    // Gesten (16.4)
    langeBeruehrung(this.liste, (t) => zeileVon(t), (z, x, y) => {
      const id = Number(z.dataset.id);
      if (!this.auswahl.has(id)) { this.auswahl = new Set([id]); this.anker = id; }
      this.fokussieren(id, false);
      this.menue(x, y, z);
    });
    let w = null;
    this.liste.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) { w = null; return; }
      const z = zeileVon(e.target);
      w = z ? { z, x: e.touches[0].clientX, y: e.touches[0].clientY, t: performance.now() } : null;
    }, { passive: true });
    this.liste.addEventListener("touchmove", (e) => {
      if (!w) return;
      w.ex = e.touches[0].clientX;
      w.ey = e.touches[0].clientY;
      // waagerechtes Wischen ist eine Geste, kein Scrollen (sonst verschluckt ein Nachlauf das nächste Tippen)
      const dx = Math.abs(w.ex - w.x);
      if (dx > 10 && dx > Math.abs(w.ey - w.y) && e.cancelable) e.preventDefault();
    }, { passive: false });
    this.liste.addEventListener("touchend", (e) => {
      if (!w || w.ex === undefined) { w = null; return; }
      const dx = w.ex - w.x;
      const dy = Math.abs(w.ey - w.y);
      const dt = performance.now() - w.t;
      const z = w.z;
      w = null;
      if (Math.abs(dx) < 80 || dy > 40 || dt > 1000) return;
      const id = Number(z.dataset.id);
      if (dx > 0) {
        if (this.auswahl.has(id)) this.auswahl.delete(id); else this.auswahl.add(id);
        this.anker = id;
        this.fokussieren(id, false);
      } else {
        const ids = this.auswahl.has(id) ? this.ids().filter((x) => this.auswahl.has(x)) : [id];
        this.kategorieWaehlen(ids, z);
      }
    });
  }

  // ---------------------------------------------------------------- Kontextmenü (8.2)
  auswahlIds() { return this.ids().filter((x) => this.auswahl.has(x)); }

  menue(x, y, ausloeser, alt = false) {
    const ids = this.auswahlIds();
    const eine = ids.length === 1;
    const mitVorschlag = this.eintraege.some((b) => this.auswahl.has(b.id) && b.vorschlag);
    const verdacht = eine ? this.verdachte.find((v) => v.buchung_id === ids[0] || v.kandidat_ids.includes(ids[0])) : null;
    const b = eine ? this.eintraege.find((x2) => x2.id === ids[0]) : null;
    kontextmenue(x, y, [
      { tid: "km-kategorie", text: "Kategorie setzen…", tun: () => this.kategorieWaehlen(ids, ausloeser) },
      { tid: "km-tags", text: "Tags…", tun: () => tagAuswahl(ids, ausloeser) },
      { tid: "km-splitten", text: "Splitten…", aktiv: eine, tun: () => splitDialog(b, ausloeser) },
      { tid: "km-dublette", text: "Als Dublette markieren…", aktiv: !!verdacht, tun: () => dubletteDialog(verdacht, ausloeser) },
      { tid: "km-vorschlag-annehmen", text: "Vorschlag annehmen", aktiv: mitVorschlag, tun: () => this.vorschlag(null, ids, "annehmen") },
      { tid: "km-vorschlag-ablehnen", text: "Vorschlag ablehnen", aktiv: mitVorschlag, tun: () => this.vorschlag(null, ids, "ablehnen") },
      { tid: "km-bearbeiten", text: "Verwendungszweck bearbeiten", aktiv: eine, tun: () => this.bearbeiten(ids[0], "verwendungszweck") },
      { tid: "km-status", text: "Status setzen…", tun: () => this.statusWaehlen(ids, ausloeser) },
      { tid: "km-mehrfach", text: "Bearbeiten…", tun: () => this.mehrfachDialog(ids, ausloeser) },
      this.gegenbuchungEintrag(b, x, y, ausloeser),
      ...(this.istKategorie ? [] : [{ tid: "km-verschieben", text: "Auf anderes Konto verschieben…",
        tun: () => this.verschiebenDialog(ids, ausloeser) }]),
      { tid: "km-loeschen", text: "Löschen…", tun: () => this.loeschen(ausloeser) },
      // Versteckt (D-116): nur mit gedrückter Alt-Taste
      alt ? { tid: "km-wiederkehrend", text: "Warum (nicht) wiederkehrend?", aktiv: eine,
        tun: () => begruendungZeigen(ids[0], ausloeser) } : null,
    ].filter(Boolean), ausloeser);
  }

  // ---------------------------------------------------------------- Gehe zur Gegenbuchung (D-119)
  /** Konten der übrigen Splits einer Buchung (ohne dieses Konto), in Split-Reihenfolge, ohne Doppelte. */
  gegenkonten(b) {
    const ids = [];
    for (const sp of (b && b.splits) || []) {
      if (sp.konto_id !== this.konto.id && !ids.includes(sp.konto_id)) ids.push(sp.konto_id);
    }
    return ids;
  }

  gegenbuchungEintrag(b, x, y, ausloeser) {
    const ziele = this.gegenkonten(b);
    const mehrere = ziele.length > 1;
    return { tid: "km-gegenbuchung", text: mehrere ? "Gehe zur Gegenbuchung…" : "Gehe zur Gegenbuchung",
      aktiv: ziele.length > 0, tun: () => {
        if (!mehrere) return oberflaeche.zurBuchung(ziele[0], b.id);
        // mehrere Gegenseiten: Auswahl als Untermenü an derselben Stelle
        return kontextmenue(x, y, ziele.map((k) => ({ tid: `km-gegenbuchung-${k}`, text: pfadVon(k) || `Konto ${k}`,
          tun: () => oberflaeche.zurBuchung(k, b.id) })), ausloeser);
      } };
  }

  /** Buchung in dieser Ansicht zeigen: weitere Seiten laden, nötigenfalls Filter zurücksetzen, dann markieren. */
  async buchungZeigen(id) {
    const da = () => this.eintraege.some((b) => b.id === id);
    const nachladen = async () => {
      while (!da() && this.eintraege.length < this.gesamt) { this.seiten += 1; await this.laden(); }
    };
    await nachladen();
    if (!da() && this.filterAnzahl() > 0) {
      this.filter = this.filter.sortierung ? { sortierung: this.filter.sortierung } : {};
      this.seiten = 1;
      this.urlSchreiben();
      const leiste = this.filterAufbauen();
      this.filterLeiste.replaceWith(leiste);
      this.filterLeiste = leiste;
      await this.laden();
      await nachladen();
      if (da()) melde("hinweis", "Filter zurückgesetzt, damit die Buchung sichtbar ist.");
    }
    if (!da()) { melde("fehler", "Die Buchung ist in dieser Ansicht nicht enthalten."); return; }
    this.sprungMarkieren(id);
  }

  /**
   * Sprungziel (D-118, Gegenbuchung, Berichte): wählen, fokussieren, in die Mitte rollen und kurz hervorheben. Mitte
   * statt „nearest“, weil am Rand sonst die Mehrfachleiste (mobil unten fest) die Zeile verdecken kann (D-129).
   */
  sprungMarkieren(id) {
    this.auswahl = new Set([id]);
    this.anker = id;
    this.fokussieren(id);
    const z = this.zeilen.get(id);
    if (!z) return;
    const links = this.listenSpalte ? this.listenSpalte.scrollLeft : 0;
    z.scrollIntoView({ block: "center" });
    if (this.listenSpalte) this.listenSpalte.scrollLeft = links;
    z.classList.add("sprung-ziel");
    setTimeout(() => z.classList.remove("sprung-ziel"), 2000);
  }

  // ---------------------------------------------------------------- Mehrfachbearbeitung (7.5)
  mehrfachAufbauen() {
    const k = (testid, text, tun) => knopf(text, { tid: testid, onclick: (e) => tun(e.currentTarget) });
    return h("div", { class: "mehrfach-leiste", tid: "mehrfach-leiste", role: "toolbar", "aria-label": "Auswahl bearbeiten",
      hidden: true },
    k("mehrfach-kategorie", "Kategorie…", (el) => this.kategorieWaehlen(this.auswahlIds(), el)),
    k("mehrfach-tags", "Tags…", (el) => tagAuswahl(this.auswahlIds(), el)),
    k("mehrfach-status", "Status…", (el) => this.statusWaehlen(this.auswahlIds(), el)),
    k("mehrfach-bearbeiten", "Bearbeiten…", (el) => this.mehrfachDialog(this.auswahlIds(), el)),
    k("mehrfach-vorschlag-annehmen", "Vorschläge annehmen", () => this.vorschlag(null, this.auswahlIds(), "annehmen")),
    k("mehrfach-vorschlag-ablehnen", "Vorschläge ablehnen", () => this.vorschlag(null, this.auswahlIds(), "ablehnen")),
    this.istKategorie ? null : k("mehrfach-verschieben", "Verschieben…", (el) => this.verschiebenDialog(this.auswahlIds(), el)),
    k("mehrfach-loeschen", "Löschen…", (el) => this.loeschen(el)),
    k("auswahl-aufheben", "Auswahl aufheben", () => { this.auswahl.clear(); this.auswahlZeigen(); }));
  }

  async kategorieWaehlen(ids, ausloeser) {
    if (!ids.length) return;
    const kat = await kategorieAuswahl(ids.length === 1 ? "Kategorie setzen" : `Kategorie für ${ids.length} Buchungen`,
      ausloeser);
    if (kat) await this.kategorieSetzen(ids, kat);
  }

  async kategorieSetzen(ids, kategorieId) {
    const sortiert = ids.slice().sort((a, b) => a - b);
    try {
      await aktion(() => (sortiert.length === 1
        ? api("PUT", `/api/buchungen/${sortiert[0]}/kategorie`, { kategorie_id: kategorieId })
        : api("POST", "/api/buchungen/mehrfach/kategorie", { buchung_ids: sortiert, kategorie_id: kategorieId })),
      { erfolg: `Kategorie „${pfadVon(kategorieId)}“ gesetzt.` });
    } catch (e) { /* gemeldet, Liste zeigt den Stand des Servers */ }
  }

  async vorschlag(e, ids, was) {
    if (e) { e.stopPropagation(); }
    const mit = this.eintraege.filter((b) => ids.includes(b.id) && b.vorschlag).map((b) => b.id).sort((a, b) => a - b);
    if (!mit.length) return;
    try {
      await aktion(() => (mit.length === 1 && e
        ? api("POST", `/api/buchungen/${mit[0]}/vorschlag`, { aktion: was })
        : api("POST", "/api/buchungen/mehrfach/vorschlag", { buchung_ids: mit, aktion: was })),
      { erfolg: was === "annehmen" ? "Vorschlag angenommen." : "Vorschlag abgelehnt." });
    } catch (f) { /* gemeldet */ }
  }

  // ---------------------------------------------------------------- Status und Bearbeiten-Dialog (23.3 bis 23.5)
  abgeglichenUnter(ids, status) {
    return this.eintraege.filter((b) => ids.includes(b.id) && b.status === "abgeglichen" && status !== "abgeglichen");
  }

  async statusWaehlen(ids, ausloeser) {
    if (!ids.length) return;
    const status = await statusAuswahl(ids.length, ausloeser);
    if (status) await this.statusSetzen(ids, status, ausloeser);
  }

  /** Status über mehrfach/aendern; vor dem Verlassen von „abgeglichen“ eine Rückfrage (E-169). */
  async statusSetzen(ids, status, ausloeser) {
    const sortiert = ids.slice().sort((a, b) => a - b);
    const abgeglichen = this.abgeglichenUnter(sortiert, status);
    const koerper = { buchung_ids: sortiert, status };
    if (abgeglichen.length) {
      const n = abgeglichen.length;
      const ok = await bestaetigen(n === 1 && sortiert.length === 1
        ? "Die Buchung ist abgeglichen. Nach der Statusänderung kann sie bearbeitet werden. Fortfahren?"
        : `${n === 1 ? "1 Buchung ist" : `${n} Buchungen sind`} abgeglichen. Nach der Statusänderung können sie `
          + "bearbeitet werden. Fortfahren?", { ja: "Status ändern", ausloeser });
      if (!ok) return;
      koerper.entsperren = true;
    }
    try {
      await aktion(() => api("POST", "/api/buchungen/mehrfach/aendern", koerper),
        { erfolg: `Status „${STATUS_TEXT[status]}“ gesetzt.` });
    } catch (e) { /* gemeldet; atomar, nichts geändert */ }
  }

  mehrfachDialog(ids, ausloeser) {
    if (!ids.length) return;
    const sortiert = ids.slice().sort((a, b) => a - b);
    dialog("mehrfach-dialog", sortiert.length === 1 ? "Buchung bearbeiten" : `${sortiert.length} Buchungen bearbeiten`,
      (inhalt, d) => {
        const werte = {
          status: statusSelect("Status", "mehrfach-wert-status"),
          datum: h("input", { type: "date", tid: "mehrfach-wert-datum" }),
          empfaenger: empfaengerSelect("Empfänger", "mehrfach-wert-empfaenger"),
          verwendungszweck: h("input", { type: "text", tid: "mehrfach-wert-verwendungszweck", maxlength: "10000" }),
        };
        const titel = { status: "Status", datum: "Datum", empfaenger: "Empfänger", verwendungszweck: "Verwendungszweck" };
        const entsperren = h("input", { type: "checkbox", tid: "mehrfach-entsperren" });
        const entsperrenZeile = h("label", { class: "feld", hidden: true }, entsperren,
          " Abgeglichene Buchungen entsperren (Status ändern)");
        const uebernehmen = knopf("Übernehmen", { tid: "mehrfach-uebernehmen", class: "knopf knopf-haupt", disabled: true });
        const pruefen = () => {
          const zeigen = an.status.checked && this.abgeglichenUnter(sortiert, werte.status.value).length > 0;
          entsperrenZeile.hidden = !zeigen;
          const irgendeins = Object.values(an).some((x) => x.checked);
          uebernehmen.disabled = !irgendeins || (an.datum.checked && !werte.datum.value)
            || (zeigen && !entsperren.checked);
        };
        entsperren.addEventListener("change", pruefen);
        const an = {};
        const zeilen = Object.keys(werte).map((f) => {
          an[f] = h("input", { type: "checkbox", tid: `mehrfach-an-${f}`, "aria-label": `${titel[f]} ändern` });
          werte[f].id = neueId("mehrfach");
          for (const t of ["input", "change"]) werte[f].addEventListener(t, () => { an[f].checked = true; pruefen(); });
          an[f].addEventListener("change", pruefen);
          return h("div", { class: "feld mehrfach-feld" }, h("label", { for: werte[f].id }, an[f], " ", titel[f]),
            werte[f]);
        });
        uebernehmen.addEventListener("click", () => imDialog(d, uebernehmen, async () => {
          pruefen();
          if (uebernehmen.disabled) return;
          const k = { buchung_ids: sortiert };
          if (an.status.checked) k.status = werte.status.value;
          if (an.datum.checked) k.datum = werte.datum.value;
          if (an.empfaenger.checked) k.empfaenger_id = werte.empfaenger.value === "" ? null : Number(werte.empfaenger.value);
          if (an.verwendungszweck.checked) k.verwendungszweck = werte.verwendungszweck.value;
          if (!entsperrenZeile.hidden && entsperren.checked) k.entsperren = true;
          await aktion(() => api("POST", "/api/buchungen/mehrfach/aendern", k), { stillBeiFehler: true,
            danach: () => d.schliessen(true),
            erfolg: sortiert.length === 1 ? "Buchung geändert." : `${sortiert.length} Buchungen geändert.` });
        }));
        inhalt.append(h("p", null, h("span", { tid: "mehrfach-dialog-anzahl", "data-anzahl": String(sortiert.length) },
          sortiert.length === 1 ? "1 Buchung" : `${sortiert.length} Buchungen`), " ausgewählt. Angehakte Felder werden "
          + "bei allen gesetzt."), ...zeilen, entsperrenZeile,
        knopfLeiste(uebernehmen, knopf("Abbrechen", { tid: "mehrfach-abbrechen", onclick: () => d.schliessen(null) })));
      }, { ausloeser });
  }

  // ---------------------------------------------------------------- Verschieben (D-110)
  async verschiebenDialog(ids, ausloeser) {
    const ziele = baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art) && k.id !== this.konto.id)).map((x) => x.konto);
    if (!ziele.length) { melde("hinweis", "Es gibt kein weiteres Bestandskonto."); return; }
    let herkunft = [];
    try { herkunft = await api("GET", `/api/konten/${this.konto.id}/herkunft`); } catch (e) { /* ohne Herkunft */ }
    const sortiert = ids.slice().sort((a, b) => a - b);
    dialog("verschieben-dialog", "Buchungen verschieben", (inhalt, d) => {
      const ziel = h("select", { tid: "verschieben-ziel" }, h("option", { value: "" }, "– Zielkonto wählen –"),
        ziele.map((k) => h("option", { value: String(k.id) }, kontoPfad(k))));
      const name = "verschieben-umfang";
      const radio = (wert, text, attrs) => h("label", { class: "auswahl-zeile" },
        h("input", { type: "radio", name, value: wert, tid: `verschieben-${wert}`, ...(attrs || {}) }), " ", text);
      const herkunftWahl = h("select", { tid: "verschieben-herkunft-wahl", disabled: true },
        herkunft.map((x) => h("option", { value: x.gruppe }, `${x.beschreibung}${x.zeitpunkt ? ` (${datumText(x.zeitpunkt.slice(0, 10))})` : ""}`
          + ` – ${x.anzahl === 1 ? "1 Buchung" : `${x.anzahl} Buchungen`}`)));
      const rAuswahl = radio("auswahl", sortiert.length === 1 ? "Die ausgewählte Buchung" : `Die ${sortiert.length} ausgewählten Buchungen`,
        { disabled: !sortiert.length, checked: !!sortiert.length });
      const rHerkunft = radio("herkunft", "Alle Buchungen dieses Kontos aus einem Import oder einer Synchronisation:",
        { disabled: !herkunft.length, checked: !sortiert.length && !!herkunft.length });
      const umfang = () => (inhalt.querySelector(`input[name='${name}']:checked`) || {}).value;
      const ok = knopf("Verschieben", { tid: "verschieben-ok", class: "knopf knopf-haupt" });
      const aktualisieren = () => {
        herkunftWahl.disabled = umfang() !== "herkunft";
        ok.disabled = !ziel.value || !umfang();
      };
      inhalt.addEventListener("change", aktualisieren);
      ok.addEventListener("click", () => imDialog(d, ok, async () => {
        const k = { von_konto_id: this.konto.id, nach_konto_id: Number(ziel.value) };
        if (umfang() === "auswahl") k.buchung_ids = sortiert; else k.gruppe = herkunftWahl.value;
        const zielName = pfadVon(k.nach_konto_id);
        await aktion(() => api("POST", "/api/buchungen/mehrfach/verschieben", k), { stillBeiFehler: true,
          danach: () => d.schliessen(true),
          erfolg: (r) => `${r && r.anzahl === 1 ? "1 Buchung" : `${r ? r.anzahl : ""} Buchungen`} nach „${zielName}“ verschoben.` });
      }));
      inhalt.append(...[feld("Zielkonto", ziel), h("fieldset", { class: "umfang" }, h("legend", null, "Welche Buchungen?"),
        rAuswahl, rHerkunft, herkunftWahl),
      !sortiert.length && !herkunft.length ? h("p", { class: "hinweis" }, "Bitte zuerst Buchungen auswählen.") : null,
      this.konto.iban ? h("p", { class: "hinweis" }, "Hinweis: Künftige Umsätze des Bankkontos landen weiter in diesem Konto, "
        + "solange das Synchronisationskonto in den Kontoeinstellungen nicht geändert wird.") : null,
      knopfLeiste(ok, knopf("Abbrechen", { onclick: () => d.schliessen(null) }))].filter(Boolean));
      aktualisieren();
    }, { ausloeser });
  }

  async loeschen(ausloeser) {
    const ids = this.auswahlIds().sort((a, b) => a - b);
    if (!ids.length) return;
    const ok = await bestaetigen(ids.length === 1 ? "1 Buchung löschen?" : `${ids.length} Buchungen löschen?`,
      { ja: "Löschen", ausloeser });
    if (!ok) return;
    try {
      // D-109: mehrere Buchungen in einer Änderung (ein Eintrag im Änderungsprotokoll)
      await aktion(() => (ids.length === 1 ? api("DELETE", `/api/buchungen/${ids[0]}`)
        : api("POST", "/api/buchungen/mehrfach/loeschen", { buchung_ids: ids })), { erfolg: ids.length === 1 ? "Buchung gelöscht." : `${ids.length} Buchungen gelöscht.` });
    } catch (e) { /* gemeldet */ }
  }

  // ---------------------------------------------------------------- Inline-Bearbeitung (7.6)
  bearbeiten(id, feld) {
    let b = this.eintraege.find((x) => x.id === id);
    let z = this.zeilen.get(id);
    if (!b || !z) return;
    // 23.2: der Status ist auch bei gesperrten Buchungen bearbeitbar
    if (feld !== "status" && (b.abgestimmt || b.status === "abgeglichen")) {
      melde("hinweis", "Diese Buchung ist abgestimmt bzw. abgeglichen und kann nicht bearbeitet werden.");
      return;
    }
    if (feld === "betrag" && !this.betragBearbeitbar(b)) {
      melde("hinweis", "Den Betrag dieser Buchung über „Splitten…“ bearbeiten.");
      return;
    }
    const gegen = gegensplits(b);
    if (feld === "kategorie" && gegen.length !== 1) {
      melde("hinweis", "Gesplittete Buchungen über „Splitten…“ bearbeiten.");
      return;
    }
    let zelle = z.querySelector(`[data-feld="${feld}"]`);
    let editor;
    let alt;
    if (feld === "datum") {
      alt = b.datum;
      editor = h("input", { type: "date", value: b.datum, "aria-label": "Datum" });
    } else if (feld === "verwendungszweck") {
      alt = b.verwendungszweck;
      editor = h("input", { type: "text", value: b.verwendungszweck, "aria-label": "Verwendungszweck" });
    } else if (feld === "status") {
      alt = b.status;
      editor = statusSelect("Status");
      editor.value = alt;
    } else if (feld === "empfaenger") {
      alt = b.empfaenger ? String(b.empfaenger.id) : "";
      editor = empfaengerSelect("Empfänger");
      editor.value = alt;
    } else if (feld === "betrag") {
      alt = betragEingabeText(b.betrag);
      editor = h("input", { type: "text", inputmode: "decimal", value: alt, "aria-label": "Betrag" });
    } else {
      alt = b.kategorie_id ? String(b.kategorie_id) : "";
      editor = h("select", { "aria-label": "Kategorie" }, h("option", { value: "" }, "– Kategorie wählen –"),
        kategorien().map(({ konto }) => h("option", { value: String(konto.id) }, kontoPfad(konto))));
      editor.value = alt;
    }
    editor.dataset.testid = "inline-editor";
    editor.dataset.feld = feld;
    editor.classList.add("inline-editor");
    let inhalt = [...zelle.childNodes];
    let fertig = false;
    let umzug = false;
    const zurueck = () => { if (zelle.isConnected) zelle.replaceChildren(...inhalt); };
    // Neuzeichnen der Liste während der Bearbeitung (z. B. Neuladen nach einer vorigen Aktion): der Editor zieht mit
    // Eingabe und Fokus in die neue Zeile um, statt geschlossen zu werden (D-121).
    const offen = {
      loesen: () => {
        if (fertig || !editor.isConnected) return false;
        const fokus = document.activeElement === editor;
        umzug = true;
        editor.remove();
        umzug = false;
        return fokus;
      },
      umziehen: (fokus) => {
        const neu = this.zeilen.get(id);
        const nb = this.eintraege.find((x) => x.id === id);
        const nz = neu && neu.querySelector(`[data-feld="${feld}"]`);
        if (!nz || !nb) { fertig = true; this.editorOffen = null; return; }
        b = nb; z = neu; zelle = nz;
        inhalt = [...zelle.childNodes];
        zelle.replaceChildren(editor);
        if (fokus) editor.focus({ preventScroll: true });
      },
    };
    this.editorOffen = offen;
    const uebernehmen = async (fokusZurueck, beimVerlassen) => {
      if (fertig || umzug) return;
      let cent = null;
      if (feld === "betrag" && editor.value !== alt) {
        cent = betragLesen(editor.value);
        if (cent === null || cent === "") {
          editor.setAttribute("aria-invalid", "true");   // ungültig: keine Anfrage (23.2)
          if (!beimVerlassen) return;
          cent = null;
        }
      }
      fertig = true;
      if (this.editorOffen === offen) this.editorOffen = null;
      const wert = editor.value;
      zurueck();
      if (fokusZurueck) z.focus({ preventScroll: true });
      if (wert === alt || (feld === "datum" && !wert) || (feld === "kategorie" && !wert)) return;
      if (feld === "status") { await this.statusSetzen([id], wert, z); return; }
      if (feld === "betrag" && cent === null) return;
      try {
        await aktion(() => {
          if (feld === "kategorie") return api("PUT", `/api/buchungen/${id}/kategorie`, { kategorie_id: Number(wert) });
          if (feld === "betrag") return api("PUT", `/api/buchungen/${id}/splits`, { splits: this.betragSplits(b, cent) });
          if (feld === "empfaenger") return api("PATCH", `/api/buchungen/${id}`, { empfaenger_id: wert === "" ? null : Number(wert) });
          return api("PATCH", `/api/buchungen/${id}`, { [feld]: wert });
        }, { erfolg: "Buchung geändert." });
      } catch (e) { /* gemeldet; die Zelle zeigt wieder den Stand des Servers */ }
    };
    editor.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") { e.preventDefault(); uebernehmen(true); }
      else if (e.key === "Tab") { uebernehmen(false); }
      else if (e.key === "Escape") {
        e.preventDefault(); fertig = true; if (this.editorOffen === offen) this.editorOffen = null;
        zurueck(); z.focus({ preventScroll: true });
      }
    });
    editor.addEventListener("blur", () => uebernehmen(false, true));
    if (editor.tagName === "SELECT") editor.addEventListener("change", () => uebernehmen(true));
    for (const t of ["click", "dblclick", "pointerdown", "contextmenu"]) editor.addEventListener(t, (e) => e.stopPropagation());
    zelle.replaceChildren(editor);
    editor.focus();
    if (feld === "verwendungszweck" || feld === "betrag") editor.select();
  }

  /** 23.2: nicht gesperrt, genau zwei Splits, genau einer davon auf dem Konto der Ansicht. */
  betragBearbeitbar(b) {
    return !b.abgestimmt && b.status !== "abgeglichen" && b.splits.length === 2
      && b.splits.filter((s) => s.konto_id === this.konto.id).length === 1;
  }

  /** Split auf dem Konto der Ansicht v, der andere −v; Reihenfolge, Konten und Memos bleiben. */
  betragSplits(b, v) {
    return b.splits.map((s) => ({ konto_id: s.konto_id, betrag: s.konto_id === this.konto.id ? v : -v, memo: s.memo }));
  }
}

/** Auswahl der vier Status in fester Reihenfolge (23.2, 23.5). */
function statusSelect(beschriftung, testid) {
  return h("select", { "aria-label": beschriftung, tid: testid || null },
    STATUS.map((st) => h("option", { value: st }, STATUS_TEXT[st])));
}

/** „ohne Empfänger“, dann die Empfänger in der Reihenfolge von GET /api/empfaenger (23.2). */
function empfaengerSelect(beschriftung, testid) {
  return h("select", { "aria-label": beschriftung, tid: testid || null }, h("option", { value: "" }, "– ohne Empfänger –"),
    stamm.empfaengerFolge.map((e) => h("option", { value: String(e.id) }, e.name)));
}

/** Status-Auswahl (23.4): ein Knopf je Status; Esc schließt ohne Wirkung. */
function statusAuswahl(anzahl, ausloeser) {
  const d = dialog("status-auswahl", anzahl === 1 ? "Status setzen" : `Status für ${anzahl} Buchungen`, (inhalt, dd) => {
    inhalt.append(knopfLeiste(...STATUS.map((st) => knopf(STATUS_TEXT[st], { tid: `status-waehlen-${st}`,
      onclick: () => dd.schliessen(st) }))));
  }, { ausloeser });
  return d.ergebnis;
}

/** Gegensplits (datenmodell.md 3.2): Splits auf Konten, die keine Bestandskonten sind. */
function gegensplits(b) {
  return b.splits.filter((s) => { const k = kontoNach(s.konto_id); return k && !BESTAND.has(k.art); });
}

function betragEingabeText(cent) {
  if (!Number.isFinite(cent)) return "";
  const neg = cent < 0;
  const abs = Math.abs(cent);
  return (neg ? "-" : "") + Math.trunc(abs / 100) + "," + String(abs % 100).padStart(2, "0");
}

export const _intern = { datumText };

// 22.2: Bestandskonto der Buchung – genau eines → Pfad und ID, mehrere → „Mehrere“, keines → leer.
function kontoZelle(b) {
  const ids = [...new Set(b.splits.map((s) => s.konto_id).filter((id) => {
    const k = kontoNach(id);
    return k && BESTAND.has(k.art);
  }))];
  const eins = ids.length === 1 ? ids[0] : null;
  return h("div", { role: "gridcell", class: "zelle zelle-konto", "data-feld": "konto",
    "data-konto-id": eins !== null ? String(eins) : "" },
  eins !== null ? pfadVon(eins) : ids.length > 1 ? "Mehrere" : "");
}
