/* Kontor – Kontoansicht (oberflaeche.md 7): Filter, Buchungsliste, Auswahl und Fokus, Mehrfachbearbeitung,
 * Inline-Bearbeitung, Kontextmenü, Drag and Drop auf Kategorien, Panels (15) und Gesten (16.4). */
import {
  BESTAND, STATUS_TEXT, abfrage, aktion, anhaengen, api, baumFolge, betragEingabe, betragEl, betragLesen, betragText, datumEl,
  datumText, h, kategorien, klasse,
  kontoNach, kontoPfad, melde, nameAnzeige, neueId, oberflaeche, personLesen, pfadVon, stamm, tid,
} from "./kern.js";
import {
  bestaetigen, dialog, dubletteDialog, erfassenDialog, feld, imDialog, kategorieAuswahl, kontextmenue, knopf, knopfLeiste,
  kontoEinstellungen, menuePosition, splitDialog, tagAuswahl,
} from "./ui.js";
import { kategorienBaum, langeBeruehrung, ziehbar } from "./baum.js";
import { ablageEinrichten, betrachter, dateiWaehlen, detailsAbschnitt, mailDialog } from "./dokumente.js";
import { AusdruckEingabe, markiert, sprache } from "./ausdruck.js";
import { Baukasten, ausdruckFeld, baukastenAusBaum, regelEditor } from "./regeleditor.js";
import { zweckZerlegen } from "./zweck.js";

const PRO_SEITE = 200;
const GRUPPE_SEITE = 500;          // Höchstwert der Buchungsliste; beim Gruppieren eine Seite statt vieler kleiner
const FENSTER_GRENZE = 100;        // darüber zeichnet das Blatt nur den sichtbaren Ausschnitt
const FENSTER_PUFFER = 12;
const MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];

function periodeText(schluessel) {
  if (/^\d{4}$/.test(schluessel)) return schluessel;
  if (/^\d{4}-\d{2}$/.test(schluessel)) {
    const name = MONATE[Number(schluessel.slice(5, 7)) - 1];
    return name ? `${name} ${schluessel.slice(0, 4)}` : schluessel;
  }
  return datumText(schluessel);
}

const WOCHENTAGE = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
function wochentag(iso) {
  const d = new Date(`${(iso || "").slice(0, 10)}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? "" : `${WOCHENTAGE[d.getUTCDay()]}, `;
}

/** Verwendungszweck gegliedert (zweck.js): Wichtiges sichtbar, technische Kennungen und Originaltext aufklappbar. */
const ZWECK_SICHTBAR = new Set(["karte", "zeitpunkt", "bestellung", "verfahren"]);
function zweckAnsicht(text) {
  if (!text) return h("span", { class: "leer" }, "–");
  const z = zweckZerlegen(text);
  const karte = z.angaben.find((a) => a.art === "karte");
  const kartenart = z.angaben.find((a) => a.art === "kartenart");
  const liste = (angaben) => h("dl", { class: "dk-angaben" }, angaben.flatMap((a) => [
    h("dt", null, a.name),
    h("dd", { class: a.mono ? "dk-mono" : null, title: a.wert },
      a.wert, a === karte && kartenart ? h("span", { class: "dk-kartenart" }, " · ", kartenart.wert) : null)]));
  const sichtbar = z.angaben.filter((a) => ZWECK_SICHTBAR.has(a.art) || (a === kartenart && !karte));
  const kennungen = z.angaben.filter((a) => !sichtbar.includes(a) && a !== kartenart);
  return h("div", { class: "dk-zweck" },
    z.arten.length ? h("div", { class: "dk-chips" }, z.arten.map((a) => h("span", { class: "dk-chip dk-art" }, a))) : null,
    z.texte.length ? h("div", { class: "dk-zweck-text" }, z.texte.map((t) => h("div", null, t))) : null,
    sichtbar.length ? liste(sichtbar) : null,
    kennungen.length ? h("details", { class: "dk-original klein" },
      h("summary", null, kennungen.length === 1 ? kennungen[0].name : `Referenzen (${kennungen.length})`), liste(kennungen)) : null,
    z.erkannt ? h("details", { class: "dk-original klein" }, h("summary", null, "Originaltext"),
      h("p", { class: "dk-mono" }, text)) : null);
}

/** Jahr → Monat → Tag. Jeder Knoten trägt die Buchungen seiner Periode. */
function datumBaum(eintraege, sortierung) {
  const aufsteigend = sortierung === "datum";
  const cmp = (a, b) => (aufsteigend ? a.schluessel.localeCompare(b.schluessel) : b.schluessel.localeCompare(a.schluessel));
  const jahre = new Map();
  for (const b of eintraege) {
    const tag = String(b.datum || "").slice(0, 10);
    const jahrK = tag.slice(0, 4);
    const monatK = tag.slice(0, 7);
    let jahr = jahre.get(jahrK);
    if (!jahr) jahre.set(jahrK, (jahr = { schluessel: jahrK, monate: new Map(), buchungen: [] }));
    jahr.buchungen.push(b);
    let monat = jahr.monate.get(monatK);
    if (!monat) jahr.monate.set(monatK, (monat = { schluessel: monatK, tage: new Map(), buchungen: [] }));
    monat.buchungen.push(b);
    let t = monat.tage.get(tag);
    if (!t) monat.tage.set(tag, (t = { schluessel: tag, buchungen: [] }));
    t.buchungen.push(b);
  }
  return [...jahre.values()].sort(cmp).map((jahr) => ({
    schluessel: jahr.schluessel, ebene: "jahr", buchungen: jahr.buchungen,
    kinder: [...jahr.monate.values()].sort(cmp).map((monat) => ({
      schluessel: monat.schluessel, ebene: "monat", buchungen: monat.buchungen,
      kinder: [...monat.tage.values()].sort(cmp).map((tag) => ({
        schluessel: tag.schluessel, ebene: "tag", buchungen: tag.buchungen, kinder: [],
      })),
    })),
  }));
}

function periodenBilanz(buchungen) {
  let eingang = 0;
  let ausgang = 0;
  for (const b of buchungen) {
    const c = b.betrag || 0;
    if (c > 0) eingang += c;
    else if (c < 0) ausgang += c;
  }
  return { eingang, ausgang, summe: eingang + ausgang, anzahl: buchungen.length };
}

const WISCH_WEG = 80;     // Mindestweg einer Wischgeste (16.4)
const WISCH_QUER = 40;    // höchstens so weit senkrecht
const STATUS = ["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"];
const PARAMETER = ["von", "bis", "betrag_min", "betrag_max", "empfaenger_id", "ohne_empfaenger", "verwendungszweck",
  "zweck_gleich", "zweck_aehnlich", "zweck_leer", "empfaenger_aehnlich",
  "suche", "kategorie_id", "unterkategorien", "unterkonten", "tag_id", "status", "sortierung", "filter"];
// Schnellauswahl Zeitraum des Filterausdrucks (D-178, Konzept 4.6.11): [Datumsangabe, Beschriftung]
const SCHNELL = [["heute", "Heute"], ["-7d", "7 Tage"], ["-30d", "30 Tage"], ["dieser_monat", "Dieser Monat"],
  ["letzter_monat", "Letzter Monat"], ["dieses_jahr", "Dieses Jahr"], ["letztes_jahr", "Letztes Jahr"]];
// Alte Einzelfilter, die es als Ausdruck nicht gibt: bleiben Parameter und erscheinen als Chips (D-187)
const ALTE_FILTER = { betrag_min: "Betrag ab", betrag_max: "Betrag bis", zweck_aehnlich: "Verwendungszweck ähnlich",
  empfaenger_aehnlich: "Empfänger ähnlich" };
const qText = (s) => JSON.stringify(String(s));

/** Einzelparameter früherer Adressen und Kontextmenüs (von, bis, empfaenger_id …) → Teile des Filterausdrucks. */
function alteFilterUebernehmen(f, istKategorie) {
  const teile = [];
  const nimm = (k, teil) => { if (teil) teile.push(teil); delete f[k]; };
  if (f.von) nimm("von", `datum >= ${f.von}`);
  if (f.bis) nimm("bis", `datum <= ${f.bis}`);
  if (f.empfaenger_id) {
    const e = stamm.empfaenger.find((x) => String(x.id) === f.empfaenger_id);
    if (e) nimm("empfaenger_id", `empf == ${qText(e.name)}`);
  }
  if (f.ohne_empfaenger) nimm("ohne_empfaenger", 'empf == ""');
  if (f.verwendungszweck) nimm("verwendungszweck", `${qText(f.verwendungszweck)} in vwz`);
  if (f.zweck_gleich) nimm("zweck_gleich", `vwz == ${qText(f.zweck_gleich)}`);
  if (f.zweck_leer) nimm("zweck_leer", 'vwz == ""');
  if (f.suche) nimm("suche", qText(f.suche));
  if (f.kategorie_id && !f.unterkategorien) {
    const k = kontoNach(Number(f.kategorie_id));
    if (k) nimm("kategorie_id", `${istKategorie ? "konto" : "kategorie"} == ${qText(kontoPfad(k))}`);
  }
  if (f.tag_id) {
    const tg = stamm.tags.find((x) => String(x.id) === f.tag_id);
    if (tg) nimm("tag_id", `${qText(tg.name)} in tags`);
  }
  if (f.status) nimm("status", `status in [${f.status.map(qText).join(", ")}]`);
  if (teile.length) {
    const alt = f.filter && /\bor\b|\|\|/.test(f.filter) ? `(${f.filter})` : f.filter;
    f.filter = [alt, ...teile].filter(Boolean).join(" and ");
  }
  return f;
}

const SCHNELL_TEIL = /^(?:datum|dt)\s+(?:in|==)\s+(?:heute|[+-]\d+[dwmqy]|dieser_monat|letzter_monat|dieses_jahr|letztes_jahr|vorjahr)$/i;
// Tastaturkürzel des Kontoblatts (D-167): [Vortaste, Taste, Text, Wirkung]. Ohne Vortaste wirken sie auf die
// markierten Buchungen; „f“ führt zu den Filtern, „v“ zur Ansicht. Groß-/Kleinschreibung zählt (Umschalt).
const KUERZEL = [
  ["", "k", "Kategorie setzen…", (s) => s.mitZielen((ids, el) => s.kategorieWaehlen(ids, el))],
  ["", "t", "Tags…", (s) => s.mitZielen((ids, el) => tagAuswahl(ids, el))],
  ["", "s", "Status setzen…", (s) => s.mitZielen((ids, el) => s.statusWaehlen(ids, el))],
  ["", "b", "Als ich bestätigen / zurücknehmen", (s) => s.mitZielen((ids) => {
    const e = s.bestaetigenEintrag(ids);
    if (e) e.tun(); else melde("hinweis", "Bitte oben rechts wählen, wer du bist.");
  })],
  ["", "a", "Vorschlag annehmen", (s) => s.mitZielen((ids) => s.vorschlagTaste(ids, "annehmen"))],
  ["", "A", "Vorschlag ablehnen", (s) => s.mitZielen((ids) => s.vorschlagTaste(ids, "ablehnen"))],
  ["", "e", "Bearbeiten… (mehrere Felder)", (s) => s.mitZielen((ids, el) => s.mehrfachDialog(ids, el))],
  ["", "x", "Splitten…", (s) => s.mitZielen((ids, el) => s.einzeln(ids, (b) => splitDialog(b, el)))],
  ["", "d", "Als Dublette markieren…", (s) => s.mitZielen((ids, el) => {
    const d = s.dubletteFuer(ids);
    if (d) dubletteDialog(d, el); else melde("hinweis", "Dafür eine Buchung mit Verdacht oder genau zwei Buchungen markieren.");
  })],
  ["", "g", "Gehe zur Gegenbuchung", (s) => s.mitZielen((ids, el) => s.einzeln(ids, (b) => {
    const [x, y] = menuePosition(null, el);
    const e = s.gegenbuchungEintrag(b, x, y, el);
    if (e.aktiv) e.tun(); else melde("hinweis", "Die Buchung hat keine Gegenbuchung.");
  }))],
  ["", "m", "Dokument anhängen…", (s) => s.mitZielen((ids) => dateiWaehlen(ids))],
  ["", "M", "E-Mail anhängen…", (s) => s.mitZielen((ids, el) => mailDialog(ids, el))],
  ["", "n", "Neue Buchung erfassen", (s) => erfassenDialog(s.konto.id, tid("buchung-erfassen", s.seite))],
  ["f", "f", "Filter-Baukasten ein/aus", (s) => s.filterLeisteTaste()],
  ["f", "u", "mit Unterkonten ein/aus", (s) => s.filterSetzen("unterkonten", s.filter.unterkonten === "true" ? "" : "true")
    .then(() => s.filterLeisteNeu())],
  ["f", "U", "mit Unterkategorien ein/aus", (s) => (s.istKategorie ? melde("hinweis", "In einer Kategorie gibt es diesen Filter nicht.")
    : s.filterSetzen("unterkategorien", s.filter.unterkategorien === "true" ? "" : "true").then(() => s.filterLeisteNeu()))],
  [`f`, ".", "gleicher Empfänger wie die markierte Buchung", (s) => s.filterWieBuchung("km-filter-empfaenger")],
  ["f", ",", "gleicher Verwendungszweck", (s) => s.filterWieBuchung("km-filter-zweck")],
  ["f", ";", "ähnlicher Verwendungszweck", (s) => s.filterWieBuchung("km-filter-zweck-aehnlich")],
  ["f", "h", "Zeitraum: heute", (s) => s.zeitraumSetzen("heute")],
  ["f", "w", "Zeitraum: letzte 7 Tage", (s) => s.zeitraumSetzen("-7d")],
  ["f", "d", "Zeitraum: letzte 30 Tage", (s) => s.zeitraumSetzen("-30d")],
  ["f", "m", "Zeitraum: dieser Monat", (s) => s.zeitraumSetzen("dieser_monat")],
  ["f", "l", "Zeitraum: letzter Monat", (s) => s.zeitraumSetzen("letzter_monat")],
  ["f", "j", "Zeitraum: dieses Jahr", (s) => s.zeitraumSetzen("dieses_jahr")],
  ["f", "J", "Zeitraum: letztes Jahr", (s) => s.zeitraumSetzen("letztes_jahr")],
  ["f", "x", "Zeitraum entfernen", (s) => s.zeitraumSetzen(null)],
  ["f", "a", "Filterausdruck", (s) => { if (s.ausdruckEingabe) s.ausdruckEingabe.eingabe.focus(); }],
  ["f", "0", "alle Filter zurücksetzen", (s) => { const k = tid("filter-zuruecksetzen", s.filterLeiste); if (k) k.click(); }],
  ["v", "g", "Gruppierung: keine ↔ nach Datum", (s) => s.gruppierungSetzen(s.gruppierung ? "" : "datum")],
  ["v", "+", "alle Gruppen aufklappen", (s) => s.alleKlappen(false)],
  ["v", "-", "alle Gruppen zuklappen", (s) => s.alleKlappen(true)],
  ["v", "o", "Sortierspalte wechseln", (s) => s.sortierungWechseln(false)],
  ["v", "r", "Sortierrichtung umkehren", (s) => s.sortierungWechseln(true)],
  ["v", "d", "Panel Einzelheiten ein-/ausklappen", (s) => s.panelUmschalten("details")],
  ["v", "k", "Panel Kategorien ein-/ausklappen", (s) => s.panelUmschalten("kategorien")],
  ["v", "a", "Spaltenbreiten an den Inhalt anpassen", (s) => s.spalteAnpassen(s.spalten.map(([f]) => f))],
  ["v", "0", "Spaltenbreiten zurücksetzen", (s) => s.spaltenZuruecksetzen()],
  ["v", ",", "Konto-Einstellungen…", (s) => kontoEinstellungen(s.konto, tid("konto-einstellungen-oeffnen", s.seite))],
];
const VORTASTEN = { f: "Filter", v: "Ansicht" };

/** Kürzel des Kontoblatts für Hilfe und Befehlspalette: [Tastenfolge, Gruppe, Text]. */
export function kontoKuerzel() {
  return KUERZEL.map(([vor, taste, text]) => [vor ? `${vor} ${taste}` : taste, vor ? VORTASTEN[vor] : "Markierte Buchungen", text]);
}

const SPALTEN = [["datum", "Datum", true], ["empfaenger", "Empfänger", true], ["verwendungszweck", "Verwendungszweck"],
  ["kategorie", "Kategorie"], ["tags", "Tags"], ["status", "Status"], ["betrag", "Betrag", true]];
// M11 (oberflaeche.md 22.2): Kontoansicht einer Kategorie mit zusätzlicher Spalte „Konto“ nach „Kategorie“
const SPALTEN_KATEGORIE = [...SPALTEN.slice(0, 4), ["konto", "Konto"], ...SPALTEN.slice(4)];

// ------------------------------------------------------------------ Spaltenbreiten (D-130)
// Je Liste (Bestandskonto „konto“, Kategorie „kategorie“) die Breite jeder Spalte in Pixeln, im Browser gemerkt.
// Ohne gemerkte Breiten gilt das Raster aus app.css; das erste Ziehen legt alle Spalten auf ihre aktuelle Breite fest.
const SPALTEN_SCHLUESSEL = "kontor.spalten";
const SPALTE_MIN = 40;
const SPALTE_MAX = 1200;
const SPALTE_ERSATZ = 120;

function spaltenAlle() {
  try {
    const s = JSON.parse(localStorage.getItem(SPALTEN_SCHLUESSEL));
    return s && s.version === 1 && s.listen && typeof s.listen === "object" ? s : { version: 1, listen: {} };
  } catch (e) {
    return { version: 1, listen: {} };
  }
}

function spaltenLaden(variante) {
  const roh = spaltenAlle().listen[variante];
  const aus = {};
  if (roh && typeof roh === "object") {
    for (const [f, w] of Object.entries(roh)) if (Number.isInteger(w) && w >= SPALTE_MIN && w <= SPALTE_MAX) aus[f] = w;
  }
  return aus;
}

function spaltenSpeichern(variante, breiten) {
  const s = spaltenAlle();
  if (Object.keys(breiten).length) s.listen[variante] = { ...breiten }; else delete s.listen[variante];
  try { localStorage.setItem(SPALTEN_SCHLUESSEL, JSON.stringify(s)); } catch (e) { /* Speicher nicht verfügbar */ }
}

const spalteBegrenzen = (w) => Math.min(SPALTE_MAX, Math.max(SPALTE_MIN, Math.round(w)));

// ------------------------------------------------------------------ Markierung der Zeilen (D-130)
const UNKATEGORISIERT = "kontor:unkategorisiert";

/** Bearbeitungsstand einer Buchung: abgeglichen (grün-grau), Kategorie zugewiesen (grün), importiert (grau). */
function markierung(b) {
  if (b.status === "abgeglichen" || b.abgestimmt) return "abgeglichen";
  const unk = stamm.konten.find((k) => k.extern_id === UNKATEGORISIERT);
  if (!b.splits.some((s) => unk && s.konto_id === unk.id)) return "kategorisiert";
  if (b.status === "importiert") return "importiert";
  return null;
}

const MAIL_GRUENDE = ["bestellung", "paypal", "rueckerstattung"];
const ERWARTUNG_ZUSTAENDE = ["offen", "erfuellt", "guthaben", "storniert", "erledigt"];
const GRUND_TEXT = { bestellung: "Bestellung", paypal: "PayPal-Zahlung", rueckerstattung: "Rückerstattung" };

function erwartungText(e) {
  return [GRUND_TEXT[e.grund] || e.grund, e.haendler, e.kennung].filter(Boolean).join(" ");
}

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
const ROLLE_TEXT = { glied: "Glied", zusaetzlich: "zusätzlich", vor_beginn: "vor Beginn", keine_serie: "–",
  anderer_betrag: "anderer Betrag" };
const FILTER_MODI = [["vorgabe", "wie Vorgabe"], ["toleranz", "Toleranz in Prozent"], ["mindestschwelle", "Mindestbetrag"],
  ["aus", "aus (jeder Betrag zählt)"]];

/** Kurzer Text zu einem Betragsfilter {modus, toleranz_prozent, mindestbetrag} (D-137). */
export function filterText(f) {
  if (f.modus === "toleranz") return `Toleranz ±${f.toleranz_prozent} %`;
  if (f.modus === "mindestschwelle") return `nur Beträge ab ${betragText(f.mindestbetrag)}`;
  return "aus (jeder Betrag zählt)";
}

/** Dialog: Betragsfilter eines Empfängers für wiederkehrende Buchungen (D-137). ``empfaenger`` = {id, name} oder
 * null (dann mit Auswahl des Empfängers). Speichern/Entfernen sind Änderungen am Buchbestand (Rückgängig). */
export async function wkFilterDialog(empfaenger, ausloeser) {
  const einst = await api("GET", "/api/wiederkehrend/einstellungen");
  const vorhanden = (id) => einst.empfaenger.find((x) => x.empfaenger.id === id) || null;
  const v = einst.vorgabe;
  dialog("wk-filter-dialog", empfaenger ? `Betragsfilter für „${empfaenger.name}“` : "Betragsfilter für einen Empfänger",
    (inhalt, d) => {
      const wahl = h("select", { tid: "wk-filter-empfaenger" }, stamm.empfaenger.map((e) => h("option", { value: String(e.id) }, e.name)));
      const modus = h("select", { tid: "wk-filter-modus" }, FILTER_MODI.map(([w, t]) => h("option", { value: w }, t)));
      const prozent = h("input", { type: "number", min: "0", max: "100", step: "1", tid: "wk-filter-toleranz", inputmode: "numeric" });
      const betrag = h("input", { type: "text", tid: "wk-filter-betrag", inputmode: "decimal", placeholder: "z. B. 2.500,00" });
      const fProzent = feld("Toleranz (%)", prozent);
      const fBetrag = feld("Mindestbetrag (€, ohne Vorzeichen)", betrag);
      const hinweis = h("p", { class: "wk-hinweis" });
      const laden = () => {
        const x = vorhanden(Number(wahl.value));
        modus.value = x ? x.modus : "vorgabe";
        prozent.value = x && x.toleranz_prozent !== null ? String(x.toleranz_prozent) : String(v.toleranz_prozent ?? 10);
        betrag.value = x && x.mindestbetrag !== null ? betragEingabe(x.mindestbetrag) : "";
        sichtbar();
      };
      const sichtbar = () => {
        fProzent.hidden = modus.value !== "toleranz";
        fBetrag.hidden = modus.value !== "mindestschwelle";
        hinweis.textContent = modus.value === "vorgabe" ? `Es gilt die Vorgabe aus den Einstellungen: ${filterText(v)}.`
          : modus.value === "mindestschwelle" ? "Kleinere Zahlungen dieses Empfängers (z. B. Erstattungen) werden übergangen."
          : modus.value === "toleranz" ? "Zahlungen, deren Betrag stärker vom vorigen Glied abweicht, werden übergangen." : "";
      };
      modus.addEventListener("change", sichtbar);
      wahl.addEventListener("change", laden);
      if (empfaenger) wahl.value = String(empfaenger.id);
      const ok = knopf("Speichern", { class: "knopf knopf-haupt", tid: "wk-filter-speichern" });
      ok.addEventListener("click", () => {
        const id = Number(wahl.value);
        let anfrage;
        if (modus.value === "vorgabe") {
          if (!vorhanden(id)) { d.schliessen(null); return; }
          anfrage = () => api("DELETE", `/api/empfaenger/${id}/wiederkehrend`);
        } else {
          const k = { modus: modus.value };
          if (modus.value === "toleranz") k.toleranz_prozent = Number(prozent.value);
          if (modus.value === "mindestschwelle") {
            const c = betragLesen(betrag.value);
            k.mindestbetrag = c === null || c === "" ? 0 : Math.abs(c);
          }
          anfrage = () => api("PUT", `/api/empfaenger/${id}/wiederkehrend`, k);
        }
        imDialog(d, ok, () => aktion(anfrage, { stillBeiFehler: true, danach: () => d.schliessen(true),
          erfolg: "Betragsfilter gespeichert." }));
      });
      inhalt.append(empfaenger ? null : feld("Empfänger", wahl), feld("Betragsfilter", modus), fProzent, fBetrag, hinweis,
        knopfLeiste(ok, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
      laden();
    }, { ausloeser });
}
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
    e.betragsfilter ? h("p", { class: "wk-hinweis", tid: "wk-betragsfilter", "data-modus": e.betragsfilter.modus,
      "data-quelle": e.betragsfilter.quelle }, e.betragsfilter_text) : null,
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
      knopfLeiste(knopf("Schließen", { tid: "wk-schliessen", onclick: () => d.schliessen(null) }),
        w.empfaenger ? knopf("Betragsfilter …", { tid: "wk-filter-oeffnen",
          "aria-label": `Betragsfilter für ${w.empfaenger.name}`, onclick: (ev) => {
            const knopfEl = ev.currentTarget;
            d.schliessen(null);
            wkFilterDialog(w.empfaenger, knopfEl.isConnected ? knopfEl : ausloeser);
          } }) : null)]);
  }, { ausloeser, klasse: "dialog-breit", schliessenKnopf: "wk-x",
    fokus: (box) => box.querySelector("[data-testid=wk-schliessen]") });
}

class Kontoansicht {
  constructor(seite, konto, suche) {
    this.seite = seite;
    this.konto = konto;
    this.istKategorie = klasse(konto) !== "bestand";   // 22.2: Kategorie oder technisches Konto
    this.spalten = this.istKategorie ? SPALTEN_KATEGORIE : SPALTEN;
    this.spaltenVariante = this.istKategorie ? "kategorie" : "konto";
    this.breiten = spaltenLaden(this.spaltenVariante);
    this.wiederkehrend = new Set();
    this.mailBestaetigt = new Map();
    this.titel = konto.name;
    this.filter = this.filterAusUrl(suche);
    this.gruppierung = this.gruppierungAusUrl(suche);
    this.zugeklappt = new Set();
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
    if (f.zweck_leer !== undefined && f.zweck_leer !== "true") delete f.zweck_leer;
    for (const p of ["unterkategorien", "unterkonten"]) if (f[p] !== undefined && f[p] !== "true") delete f[p];
    if (this.istKategorie) delete f.unterkategorien;   // 22.2: entfällt in der Kategorieansicht
    return alteFilterUebernehmen(f, this.istKategorie);
  }

  gruppierungAusUrl(suche) {
    const g = new URLSearchParams(suche || "").get("gruppierung");
    return g === "datum" || g === "tag" || g === "monat" ? "datum" : "";
  }

  get sortierung() { return this.filter.sortierung || "-datum"; }

  filterAnzahl() {
    const e = this.ausdruckEingabe && this.ausdruckEingabe.ergebnis;
    const teile = this.filter.filter ? Math.max(1, e && e.gueltig ? e.zusammenfassung.length : 1) : 0;
    return Object.keys(this.filter).filter((k) => k !== "sortierung" && k !== "filter").length + teile;
  }

  urlSchreiben() {
    const f = { ...this.filter };   // nur gesetzte Filter und eine gewählte Sortierung (7.1)
    if (this.gruppierung) f.gruppierung = this.gruppierung;   // Ansicht, kein Parameter der Buchungsliste
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
    while (!this.eintraege.some((b) => b.id === id) && this.eintraege.length < this.gesamt) {
      this.seiten += 1;
      await this.laden();
    }
    this.urlSchreiben();   // Sprungziel aus der Adresse entfernen
    if (!this.eintraege.some((b) => b.id === id)) {
      melde("hinweis", "Die Buchung ist mit den aktuellen Filtern nicht sichtbar.");
      return;
    }
    const kette = this.periodeKette(id);
    let geoeffnet = false;
    for (const k of kette) if (this.zugeklappt.delete(k)) geoeffnet = true;
    if (geoeffnet) this.listeZeichnen();
    this.sprungMarkieren(id);
  }

  async laden() {
    const nr = (this.ladeNr = (this.ladeNr || 0) + 1);   // nur die jüngste Antwort zählt
    this.seite.dataset.geladen = "nein";
    const proSeite = this.gruppierung ? GRUPPE_SEITE : PRO_SEITE;
    const basis = { konto_id: this.konto.id, ...this.filter, sortierung: this.sortierung, pro_seite: proSeite, verdacht: "ja" };
    delete basis.gruppierung;
    // D-130: Buchungen, die einer aus Mails erkannten Erwartung zugeordnet sind (Mail-Abgleich, D-128)
    const erwartungen = api("GET", "/api/erwartungen" + abfrage({ grund: MAIL_GRUENDE, zustand: ERWARTUNG_ZUSTAENDE }))
      .then((e) => e.eintraege, () => []);
    const eintraege = [];
    let gesamt = 0;
    let summe = 0;
    // Gruppiert lädt die Liste die ganze Filtermenge, damit Eingang, Ausgang und Summe einer Periode vollständig sind.
    // Die weiteren Seiten laufen parallel; ohne Gruppierung bleibt es beim seitenweisen Nachladen.
    const bis = this.gruppierung ? 100000 : this.seiten;
    const erste = await api("GET", "/api/buchungen" + abfrage({ ...basis, seite: 1 }));
    eintraege.push(...erste.eintraege);
    gesamt = erste.gesamt;
    summe = erste.summe;
    const letzte = Math.min(bis, Math.ceil(gesamt / proSeite) || 1);
    if (letzte > 1) {
      const rest = await Promise.all(Array.from({ length: letzte - 1 }, (_, i) =>
        api("GET", "/api/buchungen" + abfrage({ ...basis, seite: i + 2 }))));
      for (const s of rest) eintraege.push(...s.eintraege);
    }
    let verdachte = [];
    try { verdachte = await api("GET", "/api/dubletten?status=offen&vorschlaege=ja"); } catch (e) { verdachte = []; }
    await this.regelnLaden(eintraege);
    const mail = new Map();
    for (const e of await erwartungen) for (const id of e.buchung_ids) if (!mail.has(id)) mail.set(id, erwartungText(e));
    if (nr !== this.ladeNr) return;
    this.mailBestaetigt = mail;
    this.kandidatenCache = new Map();
    this.verdachte = verdachte;
    this.eintraege = eintraege;
    this._gruppen = null;
    this.gesamt = gesamt;
    this.summe = summe;
    const ids = new Set(eintraege.map((b) => b.id));
    for (const id of [...this.auswahl]) if (!ids.has(id)) this.auswahl.delete(id);
    if (!ids.has(this.anker)) this.anker = null;
    if (!ids.has(this.fokusId)) this.fokusId = null;
    this.listeZeichnen();
    this.zusammenfassungZeichnen();
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
        knopf("Einstellungen…", { tid: "konto-einstellungen-oeffnen", onclick: (e) => kontoEinstellungen(this.konto, e.currentTarget) }))),
    h("div", { class: "listen-info" }, this.anzahlEl, " · Summe ", this.summeEl, h("span", { class: "auswahl-trenner" }, " · "),
      this.auswahlEl, this.gruppierungLeiste()));
    s.append(this.ausdruckFilterAufbauen());
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
    this.auswahlKopf = this.auswahlKopfAufbauen();
    s.append(this.auswahlKopf);
    this.arbeit = h("div", { class: "arbeitsbereich" });
    s.append(this.arbeit);
    this.mehrfach = this.mehrfachAufbauen();
    s.append(this.mehrfach);
    this.arbeitZeichnen();
    this.listeEreignisse();
  }

  layoutGeaendert() {
    const mobil = oberflaeche.istMobil();
    this.zeilenH = 0;
    this.balkenH = 0;
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
    if (this.bkKnopf) {   // Umschalter am Ausdrucksfeld (D-188)
      this.bkKnopf.setAttribute("aria-expanded", String(this.filterSichtbar));
      this.bkKnopf.textContent = this.filterSichtbar ? "Baukasten ▾" : "Baukasten ▸";
    }
  }

  // ------------------------------------------------- Filterausdruck (D-178, Konzept 5.4)
  ausdruckFilterAufbauen() {
    let uhr;
    const anwenden = () => {
      clearTimeout(uhr);
      const t = this.ausdruckEingabe.wert.trim();
      const e = this.ausdruckEingabe.ergebnis;
      if (t && (!e || !e.gueltig)) return;   // bei Fehlern bleibt die letzte gültige Liste stehen
      this.filterSetzen("filter", t);
    };
    this.ausdruckEingabe = new AusdruckEingabe({ kontext: "filter", tid: "filter-ausdruck", wert: this.filter.filter || "",
      beschriftung: "Filter: Suchtext oder Ausdruck", platzhalter: "z. B.  rewe dt in letzter_monat and bet > 20",
      beiErgebnis: (e) => {
        this.zusammenfassungZeichnen();
        if (this.ausBaukasten) this.ausBaukasten = false; else this.baukastenAusAusdruck(e);
        clearTimeout(uhr);
        uhr = setTimeout(anwenden, 400);
      },
      beiEnter: anwenden });
    const leeren = h("button", { type: "button", class: "knopf-flach", tid: "filter-ausdruck-leeren", "aria-label": "Filterausdruck leeren",
      onclick: () => { this.ausdruckEingabe.wert = ""; anwenden(); this.ausdruckEingabe.eingabe.focus(); } }, "✕");
    const menue = h("button", { type: "button", class: "knopf-flach", tid: "filter-ausdruck-menue", "aria-haspopup": "menu",
      "aria-label": "Weitere Aktionen zum Filter" }, "⋯");
    menue.addEventListener("click", (e) => {
      const gueltig = !!(this.ausdruckEingabe.ergebnis && this.ausdruckEingabe.ergebnis.gueltig);
      const r = e.currentTarget.getBoundingClientRect();
      kontextmenue(r.left, r.bottom, [
        { tid: "km-filter-festschreiben", text: "Jahr festschreiben", aktiv: gueltig, tun: () => this.festschreiben() },
        { tid: "km-filter-als-regel", text: "Als Regel speichern…", aktiv: gueltig, tun: () => this.alsRegel(menue) },
      ], menue);
    });
    this.zusammenfassungEl = h("p", { class: "filter-zusammenfassung", tid: "filter-zusammenfassung", "aria-live": "polite" });
    const chips = h("div", { class: "filter-schnell", tid: "filter-schnell", role: "group", "aria-label": "Zeitraum" },
      SCHNELL.map(([w, text]) => h("button", { type: "button", class: "chip", tid: `filter-schnell-${w}`,
        onclick: () => this.zeitraumSetzen(w) }, text)));
    return h("div", { class: "ausdruck-filter", tid: "ausdruck-filter", role: "search", "aria-label": "Filterausdruck" },
      h("div", { class: "ausdruck-filter-zeile" }, ausdruckFeld("Filter", this.ausdruckEingabe), leeren, menue,
        this.bkKnopf = h("button", { type: "button", class: "knopf klein bk-umschalter", tid: "filter-baukasten-umschalten",
          "aria-controls": "filter-leiste", "aria-expanded": String(this.filterSichtbar),
          title: "Filter im Baukasten bearbeiten (f f)", onclick: () => this.filterUmschalten() },
        this.filterSichtbar ? "Baukasten ▾" : "Baukasten ▸")),
      this.zusammenfassungEl, chips);
  }

  /** Setzt bzw. ersetzt einen einfachen Datumsteil auf oberster Ebene (Schnellauswahl). */
  mitZeitraum(w) {
    return this.mitTeil(SCHNELL_TEIL, w === null ? null : w === "heute" ? "datum == heute" : `datum in ${w}`);
  }

  /** Ersetzt Teile auf oberster Ebene, die `muster` erfüllen, durch `neu` (null: nur entfernen). */
  mitTeil(muster, neu) {
    const t = this.ausdruckEingabe.wert.trim();
    if (!t) return neu || "";
    if (/\bor\b|\|\||[()]/.test(t)) return neu ? `(${t}) and ${neu}` : t;
    const teile = t.split(/\s+(?:and|&&)\s+/).filter((x) => !muster.test(x.trim()));
    return [...teile, neu].filter(Boolean).join(" and ");
  }

  /** Setzt den Filterausdruck und wendet ihn sofort an. */
  ausdruckSetzen(text) {
    this.ausdruckEingabe.wert = text;
    return this.filterSetzen("filter", text.trim());
  }

  zeitraumSetzen(w) { return this.ausdruckSetzen(this.mitZeitraum(w)); }

  zusammenfassungZeichnen() {
    if (!this.zusammenfassungEl) return;
    const e = this.ausdruckEingabe && this.ausdruckEingabe.ergebnis;
    const t = this.filter.filter;
    const alte = Object.entries(ALTE_FILTER).filter(([k]) => this.filter[k] !== undefined)
      .map(([k, text]) => `${text}: ${k.startsWith("betrag") ? betragText(Number(this.filter[k])) : this.filter[k]}`);
    if (!t && !alte.length) { this.zusammenfassungEl.textContent = ""; return; }
    const teile = [...(t && e && e.gueltig ? e.zusammenfassung : []), ...alte];
    this.zusammenfassungEl.textContent = [...teile, `${this.gesamt} Buchung${this.gesamt === 1 ? "" : "en"}`].join(" · ");
  }

  async festschreiben() {
    try {
      const r = await api("POST", "/api/ausdruck/pruefen", { ausdruck: this.ausdruckEingabe.wert, kontext: "filter", festschreiben: true });
      if (r.gueltig) { this.ausdruckEingabe.wert = r.kanonisch; this.filterSetzen("filter", r.kanonisch); }
    } catch (e) { melde("fehler", e.message); }
  }

  async alsRegel(ausloeser) {
    try {
      const r = await api("POST", "/api/ausdruck/als-regel", { ausdruck: this.ausdruckEingabe.wert });
      if (!r.ausdruck) { melde("hinweis", "Der Filter enthält nur Teile, die es in Regeln nicht gibt (z. B. Datum)."); return; }
      if (r.entfernt.length && !(await bestaetigen(`Nicht übernommen: ${r.entfernt.join(", ")}. Datumsangaben gibt es nur im Filter. `
        + `Die Regel lautet: ${r.ausdruck}`, { ja: "Weiter", ausloeser }))) return;
      regelEditor({ name: "", ausdruck: r.ausdruck, aktiv: true, testmenge: this.ausdruckEingabe.wert }, ausloeser);
    } catch (e) { melde("fehler", e.message); }
  }

  /** Filter-Baukasten (D-187): dieselben Zeilen wie im Regeleditor, dazu Datum und Freitext; erzeugt den
   *  Filterausdruck oben. Dazu „mit Unterkonten/-kategorien“, Chips für alte Einzelfilter und Zurücksetzen. */
  filterAufbauen() {
    const f = this.filter;
    const leiste = h("div", { class: "filter-leiste", id: "filter-leiste", tid: "filter-leiste", role: "group",
      "aria-label": "Filter-Baukasten", hidden: !this.filterSichtbar });
    // Esc im Filter: zurück zur Liste, damit es ohne Maus weitergeht (D-167)
    leiste.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      this.listeFokussieren();
    });
    const platz = h("div", { class: "filter-baukasten-platz" });
    this.bkHinweis = h("p", { class: "klein hinweis", tid: "filter-baukasten-hinweis", hidden: true });
    sprache("filter").then((sp) => {
      this.filterSp = sp;
      this.filterBaukasten = new Baukasten(sp, () => {
        this.ausBaukasten = true;
        this.ausdruckEingabe.wert = this.filterBaukasten.text();
      }, { filter: true, tid: "filter-baukasten" });
      platz.replaceChildren(this.filterBaukasten.el);
      this.baukastenAusAusdruck(this.ausdruckEingabe.ergebnis, true);
    });
    const option = (name, text, testid) => {
      const c = h("input", { type: "checkbox", tid: testid, checked: f[name] === "true" });
      c.addEventListener("change", () => this.filterSetzen(name, c.checked ? "true" : ""));
      return h("label", { class: "wahl" }, c, " " + text);
    };
    const alte = Object.entries(ALTE_FILTER).filter(([k]) => f[k] !== undefined).map(([k, text]) => {
      const wert = k.startsWith("betrag") ? betragText(Number(f[k])) : f[k];
      return h("span", { class: "chip", tid: `filter-alt-${k}` }, `${text}: ${wert} `,
        h("button", { type: "button", class: "knopf-flach", "aria-label": `${text} entfernen`,
          onclick: () => this.filterSetzen(k, "").then(() => this.filterLeisteNeu()) }, "×"));
    });
    if (f.kategorie_id) {   // nur mit Unterkategorien bleibt die Kategorie ein Einzelfilter
      alte.push(h("span", { class: "chip", tid: "filter-alt-kategorie_id" }, `${this.istKategorie ? "Konto" : "Kategorie"}: ${pfadVon(Number(f.kategorie_id))} `,
        h("button", { type: "button", class: "knopf-flach", "aria-label": "Kategorie entfernen",
          onclick: () => this.filterSetzen("kategorie_id", "").then(() => this.filterLeisteNeu()) }, "×")));
    }
    const zurueck = knopf("Filter zurücksetzen", { tid: "filter-zuruecksetzen", onclick: async () => {
      const sort = this.filter.sortierung;
      this.filter = sort ? { sortierung: sort } : {};
      this.ausBaukasten = false;
      if (this.ausdruckEingabe) this.ausdruckEingabe.wert = "";
      this.auswahl.clear();
      this.anker = null;
      this.seiten = 1;
      this.urlSchreiben();
      this.filterLeisteNeu();
      await this.laden();
    } });
    leiste.append(platz, this.bkHinweis,
      h("div", { class: "filter-optionen" },
        this.istKategorie ? null : option("unterkategorien", "mit Unterkategorien", "filter-unterkategorien"),
        option("unterkonten", "mit Unterkonten", "filter-unterkonten"),
        alte.length ? h("span", { class: "filter-alte" }, h("span", { class: "klein" }, "Weitere Filter: "), alte) : null,
        zurueck));
    return leiste;
  }

  /** Baukasten aus dem geprüften Ausdruck nachziehen (wenn der Ausdruck oben getippt wurde). */
  baukastenAusAusdruck(e, start) {
    if (!this.filterBaukasten || !this.bkHinweis) return;
    if (!e || !this.ausdruckEingabe.wert.trim()) {
      if (start || !this.filterBaukasten.text()) this.filterBaukasten.setzen(null);
      else this.filterBaukasten.setzen(null);
      this.bkHinweis.hidden = true;
      this.filterBaukasten.el.hidden = false;
      return;
    }
    if (!e.gueltig) return;
    const m = e.baukasten_faehig ? baukastenAusBaum(e.baum, this.filterSp) : null;
    this.bkHinweis.hidden = !!m;
    this.filterBaukasten.el.hidden = !m;
    if (m) this.filterBaukasten.setzen(m);
    else this.bkHinweis.textContent = "Dieser Ausdruck passt nicht in den Baukasten. Bearbeiten Sie ihn oben als Text.";
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

  /** Stift an einem Bestandteil der Einzelheiten (D-161). */
  stift(feld, label, tun, gesperrt) {
    return h("button", { type: "button", class: "stift", tid: `stift-${feld}`,
      "aria-label": label, title: gesperrt ? "Abgestimmt bzw. abgeglichen" : label,
      disabled: gesperrt || null,
      onclick: (e) => { e.stopPropagation(); tun(e.currentTarget); } }, "✎");
  }

  /** Bestandteil der Einzelheiten mit Stift; wert ist Text oder Knoten. Optional eigene Klasse und verborgener Name. */
  detailZeile(b, feld, name, wert, gesperrt, art) {
    const wertEl = h("span", { class: "details-wert" }, wert);
    return h("div", { class: `details-feld${art && art.klasse ? " " + art.klasse : ""}`, "data-feld": feld },
      h("span", { class: `details-name${art && art.ohneName ? " nur-vorlesen" : ""}` }, name), wertEl,
      this.stift(feld, `${name} bearbeiten`, () => this.detailBearbeiten(b, feld, wertEl), gesperrt));
  }

  /** Editor sitzt in der Einzelheiten-Zeile, nicht in der Liste. */
  detailBearbeiten(b, feld, wertEl) {
    if (feld !== "status" && (b.abgestimmt || b.status === "abgeglichen")) {
      melde("hinweis", "Diese Buchung ist abgestimmt bzw. abgeglichen und kann nicht bearbeitet werden.");
      return;
    }
    const id = b.id;
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
    } else return;
    editor.dataset.testid = "inline-editor";
    editor.dataset.feld = feld;
    editor.classList.add("inline-editor");
    const altKnoten = [...wertEl.childNodes];
    let fertig = false;
    const zurueck = () => { if (wertEl.isConnected) wertEl.replaceChildren(...altKnoten); };
    const uebernehmen = async () => {
      if (fertig) return;
      const wert = editor.value;
      fertig = true;
      zurueck();
      if (wert === alt || (feld === "datum" && !wert)) return;
      if (feld === "status") { await this.statusSetzen([id], wert); return; }
      try {
        await aktion(() => (feld === "empfaenger"
          ? api("PATCH", `/api/buchungen/${id}`, { empfaenger_id: wert === "" ? null : Number(wert) })
          : api("PATCH", `/api/buchungen/${id}`, { [feld]: wert })), { erfolg: "Buchung geändert." });
      } catch { /* gemeldet */ }
    };
    editor.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") { e.preventDefault(); uebernehmen(); }
      else if (e.key === "Escape") { e.preventDefault(); fertig = true; zurueck(); }
    });
    editor.addEventListener("blur", () => uebernehmen());
    if (editor.tagName === "SELECT") editor.addEventListener("change", () => uebernehmen());
    for (const t of ["click", "dblclick", "pointerdown", "contextmenu"]) editor.addEventListener(t, (e) => e.stopPropagation());
    wertEl.replaceChildren(editor);
    editor.focus();
    if (feld === "verwendungszweck") editor.select();
  }

  detailsInhalt(b) {
    if (!b) return [h("p", { class: "leer" }, "Keine Buchung gewählt.")];
    const gesperrt = !!(b.abgestimmt || b.status === "abgeglichen");
    return [
      this.detailsKopf(b, gesperrt),
      b.verdacht ? h("p", { class: "verdacht-erklaerung", tid: "verdacht-erklaerung" }, b.verdacht.text) : null,
      b.vorschlag ? this.vorschlagDetails(b) : null,
      h("section", { class: "dk-abschnitt" },
        this.detailZeile(b, "verwendungszweck", "Verwendungszweck", zweckAnsicht(b.verwendungszweck), gesperrt,
          { klasse: "dk-block" })),
      h("section", { class: "dk-abschnitt" },
        h("div", { class: "details-feld dk-block" },
          h("span", { class: "details-name" }, "Buchungssätze"),
          this.stift("splits", "Buchungssätze bearbeiten", (el) => splitDialog(b, el), gesperrt)),
        this.splitListe(b)),
      h("section", { class: "dk-abschnitt" },
        h("div", { class: "details-feld dk-block", "data-feld": "tags" },
          h("span", { class: "details-name" }, "Tags"),
          h("span", { class: "details-wert dk-tags" }, b.tags.length
            ? b.tags.map((t) => h("span", { class: "dk-chip dk-tag" }, t.name))
            : h("span", { class: "leer" }, "keine")),
          this.stift("tags", "Tags bearbeiten", (el) => tagAuswahl([b.id], el), false)),
        this.bestaetigungZeile(b)),
      detailsAbschnitt(b),
      b.extern_ids.length ? h("p", { class: "dk-herkunft klein", title: b.extern_ids.join("\n") },
        "Herkunft: ", h("span", { class: "dk-mono" }, b.extern_ids.join(", "))) : null,
    ];
  }

  /** Kopf der Einzelheiten: Empfänger und Betrag groß, darunter Datum und Status. */
  detailsKopf(b, gesperrt) {
    const eigen = b.splits.filter((s) => s.konto_id === this.konto.id);
    const betrag = eigen.length ? eigen.reduce((n, s) => n + s.betrag, 0) : null;
    const status = h("span", { class: `dk-status dk-status-${b.status}` },
      (STATUS_TEXT[b.status] || b.status) + (b.abgestimmt ? " · abgestimmt" : ""));
    return h("header", { class: `dk-kopf${betrag === null ? "" : betrag < 0 ? " dk-aus" : " dk-ein"}` },
      h("div", { class: "dk-kopf-oben" },
        this.detailZeile(b, "empfaenger", "Empfänger", b.empfaenger ? nameAnzeige(b.empfaenger.name) : h("span", { class: "leer" }, "ohne Empfänger"),
          gesperrt, { klasse: "dk-empfaenger", ohneName: true }),
        betrag === null ? null : betragEl("span", betrag, { class: "dk-betrag", tid: "details-betrag" })),
      h("div", { class: "dk-kopf-unten" },
        this.detailZeile(b, "datum", "Datum", h("span", null, h("span", { class: "dk-wochentag" }, wochentag(b.datum)), datumText(b.datum)),
          gesperrt, { klasse: "dk-datum", ohneName: true }),
        this.detailZeile(b, "status", "Status", status, false, { klasse: "dk-status-feld", ohneName: true }),
        gesperrt ? h("span", { class: "dk-schloss", title: "Abgestimmt bzw. abgeglichen – nur Status und Tags änderbar" }, "🔒") : null));
  }

  splitListe(b) {
    const unk = stamm.konten.find((k) => k.extern_id === UNKATEGORISIERT);
    return h("ul", { class: "details-splits" }, b.splits.map((s) => {
      const art = s.konto_id === this.konto.id ? " dk-split-eigen" : unk && s.konto_id === unk.id ? " dk-split-offen" : "";
      return h("li", { tid: `details-split-${s.id}`, class: `details-split${art}` },
        h("span", { class: "dk-split-konto" }, pfadVon(s.konto_id), s.memo ? h("small", null, " " + s.memo) : null),
        betragEl("span", s.betrag));
    }));
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

  // ---------------------------------------------------------------- Gruppierung (D-150)
  gruppierungLeiste() {
    const knopfArt = (art, text) => h("button", { type: "button", class: "gruppierung-knopf",
      tid: art ? `gruppierung-${art}` : "gruppierung-keine", "aria-pressed": String(this.gruppierung === art),
      onclick: () => this.gruppierungSetzen(art) }, text);
    return h("div", { class: "gruppierung-zeile" },
      h("div", { class: "gruppierung", role: "group", "aria-label": "Buchungen gruppieren" },
        knopfArt("", "Keine"), knopfArt("datum", "nach Datum")),
      knopf("Alles zusammenklappen", { tid: "gruppierung-zu", disabled: true, onclick: () => this.alleKlappen(true) }),
      knopf("Alles aufklappen", { tid: "gruppierung-auf", disabled: true, onclick: () => this.alleKlappen(false) }));
  }

  async gruppierungSetzen(art) {
    if ((art !== "" && art !== "datum") || art === this.gruppierung) return;
    this.gruppierung = art;
    this._gruppen = null;
    this.urlSchreiben();
    if (art && this.eintraege.length < this.gesamt) await this.laden();
    else this.listeZeichnen();
  }

  alleKlappen(zu) {
    if (!this.gruppierung) return;
    if (zu) this.zugeklappt = new Set(this.alleSchluessel());
    else this.zugeklappt.clear();
    this.listeZeichnen();
  }

  gruppierungKnopfZustand() {
    for (const art of ["", "datum"]) {
      const el = tid(art ? `gruppierung-${art}` : "gruppierung-keine", this.seite);
      if (el) el.setAttribute("aria-pressed", String(this.gruppierung === art));
    }
    const schluessel = this.gruppierung ? this.alleSchluessel() : [];
    const zu = tid("gruppierung-zu", this.seite);
    const auf = tid("gruppierung-auf", this.seite);
    const alleZu = schluessel.length > 0 && schluessel.every((k) => this.zugeklappt.has(k));
    const alleAuf = schluessel.length > 0 && schluessel.every((k) => !this.zugeklappt.has(k));
    if (zu) zu.disabled = !schluessel.length || alleZu;
    if (auf) auf.disabled = !schluessel.length || alleAuf;
  }

  periodeKette(id) {
    if (!this.gruppierung) return [];
    const b = this.eintraege.find((x) => x.id === id);
    if (!b) return [];
    const tag = String(b.datum || "").slice(0, 10);
    return [tag.slice(0, 4), tag.slice(0, 7), tag];
  }

  gruppen() {
    if (!this._gruppen) this._gruppen = this.gruppierung ? datumBaum(this.eintraege, this.sortierung) : [];
    return this._gruppen;
  }

  alleSchluessel() {
    const aus = [];
    for (const jahr of this.gruppen()) {
      aus.push(jahr.schluessel);
      for (const monat of jahr.kinder) {
        aus.push(monat.schluessel);
        for (const tag of monat.kinder) aus.push(tag.schluessel);
      }
    }
    return aus;
  }

  /** Sichtbare Balken und Buchungen: ein zugeklappter Knoten verbirgt seine Kinder. */
  jedenZeitraum(rueckruf) {
    if (!this.gruppierung) {
      for (const b of this.eintraege) rueckruf({ typ: "zeile", buchung: b });
      return;
    }
    for (const jahr of this.gruppen()) {
      rueckruf({ typ: "balken", gruppe: jahr });
      if (this.zugeklappt.has(jahr.schluessel)) continue;
      for (const monat of jahr.kinder) {
        rueckruf({ typ: "balken", gruppe: monat });
        if (this.zugeklappt.has(monat.schluessel)) continue;
        for (const tag of monat.kinder) {
          rueckruf({ typ: "balken", gruppe: tag });
          if (this.zugeklappt.has(tag.schluessel)) continue;
          for (const b of tag.buchungen) rueckruf({ typ: "zeile", buchung: b });
        }
      }
    }
  }

  sichtbareIds() {
    if (!this.gruppierung) return this.ids();
    const aus = [];
    this.jedenZeitraum((e) => { if (e.typ === "zeile") aus.push(e.buchung.id); });
    return aus;
  }

  gruppeUmschalten(schluessel) {
    if (this.zugeklappt.has(schluessel)) this.zugeklappt.delete(schluessel);
    else this.zugeklappt.add(schluessel);
    this.listeZeichnen();
    if (this.virtual) this.slotZeigen(`p:${schluessel}`);
    const knopf = tid(`periode-${schluessel}`, this.liste);
    if (knopf) knopf.focus();
  }

  periodenBalken(gruppe) {
    const auf = !this.zugeklappt.has(gruppe.schluessel);
    const bilanz = periodenBilanz(gruppe.buchungen);
    const id = gruppe.schluessel;
    return h("div", { class: "perioden-balken" + (auf ? "" : " zugeklappt"), role: "row", "data-periode": id,
      "data-ebene": gruppe.ebene,
      onclick: (e) => {
        if (e.target.closest("button")) return;
        this.gruppeUmschalten(id);
      } },
    h("button", { type: "button", class: "perioden-knopf", tid: `periode-${id}`, "aria-expanded": String(auf),
      onclick: () => this.gruppeUmschalten(id),
      onkeydown: (e) => {   // D-167: ← klappt zu, → klappt auf
        if ((e.key === "ArrowLeft" && auf) || (e.key === "ArrowRight" && !auf)) { e.preventDefault(); this.gruppeUmschalten(id); }
      } },
    auf ? "▾ " : "▸ ", periodeText(id)),
    h("span", { class: "perioden-zahl" }, "Eingang ", betragEl("span", bilanz.eingang, { tid: `periode-eingang-${id}` })),
    h("span", { class: "perioden-zahl" }, "Ausgang ", betragEl("span", bilanz.ausgang, { tid: `periode-ausgang-${id}` })),
    h("span", { class: "perioden-zahl" }, "Summe ", betragEl("span", bilanz.summe, { tid: `periode-summe-${id}` })),
    h("span", { class: "perioden-anzahl", tid: `periode-anzahl-${id}`, "data-anzahl": String(bilanz.anzahl) },
      bilanz.anzahl === 1 ? "1 Buchung" : `${bilanz.anzahl} Buchungen`));
  }

  // ---------------------------------------------------------------- Sichtbares Fenster (D-151)
  // Ab FENSTER_GRENZE Zeilen liegt die Liste in einem hohen Platzhalter; gezeichnet werden nur die Zeilen im Blick.
  slotsBauen() {
    const kompakt = oberflaeche.istMobil();
    if (this.hoeheKompakt !== kompakt || !this.zeilenH || !this.balkenH) {
      this.hoeheKompakt = kompakt;
      this.zeilenH = kompakt ? 56 : 32;
      this.balkenH = kompakt ? 96 : 44;
    }
    this.slotsMitHoehe();
  }

  virtualAktiv() { return this.slots.length > FENSTER_GRENZE; }

  scrollBehaelter() {
    const s = this.listenSpalte;
    if (s && getComputedStyle(s).overflowY !== "visible") return s;
    return this.seite.closest(".hauptbereich") || s || this.liste;
  }

  scrollLauschen() {
    const el = this.scrollBehaelter();
    if (this.scrollZiel === el) return;
    if (this.scrollZiel && this.beiScroll) this.scrollZiel.removeEventListener("scroll", this.beiScroll);
    this.scrollZiel = el;
    if (!this.beiScroll) {
      this.beiScroll = () => {
        if (this.editorOffen || this.scrollRahmen) return;
        this.scrollRahmen = requestAnimationFrame(() => {
          this.scrollRahmen = 0;
          this.fensterBereichZeichnen(false);
        });
      };
    }
    el.addEventListener("scroll", this.beiScroll, { passive: true });
  }

  slotSuchen(y) {
    let lo = 0;
    let hi = this.slots.length;
    while (lo < hi) {
      const m = (lo + hi) >> 1;
      if (this.slots[m].top + this.slots[m].hoehe <= y) lo = m + 1;
      else hi = m;
    }
    return lo;
  }

  sichtBereich() {
    const scroller = this.scrollBehaelter();
    const fallback = scroller.clientHeight || 800;
    if (!this.fenster) return { start: 0, ende: fallback };
    const fenster = this.fenster.getBoundingClientRect();
    const sicht = scroller.getBoundingClientRect();
    const start = Math.max(0, sicht.top - fenster.top);
    const ende = Math.min(this.listeHoehe, sicht.bottom - fenster.top);
    if (ende <= start) return { start: 0, ende: Math.min(this.listeHoehe, fallback) };
    return { start, ende };
  }

  fensterBereichZeichnen(erzwingen) {
    if (!this.virtual || !this.fensterInnen || this.editorOffen) return;
    const { start, ende } = this.sichtBereich();
    let von = Math.max(0, this.slotSuchen(start) - FENSTER_PUFFER);
    let bis = Math.min(this.slots.length, this.slotSuchen(ende) + 1 + FENSTER_PUFFER);
    if (bis < von) bis = von;
    if (!erzwingen && von === this.fensterVon && bis === this.fensterBis) return;
    this.fensterVon = von;
    this.fensterBis = bis;
    this.zeilen = new Map();
    const kompakt = oberflaeche.istMobil();
    const kinder = [];
    for (let i = von; i < bis; i++) {
      const s = this.slots[i];
      const el = s.typ === "balken" ? this.periodenBalken(s.gruppe) : this.zeile(s.buchung, kompakt);
      el.setAttribute("aria-rowindex", String(i + 2));   // Kopf = 1 (M28 7, D-170)
      kinder.push(el);
    }
    this.liste.setAttribute("aria-rowcount", String(this.slots.length + 1));
    const y = von < this.slots.length ? this.slots[von].top : 0;
    this.fensterInnen.style.transform = `translateY(${y}px)`;
    this.fensterInnen.replaceChildren(...kinder);
    this.auswahlZeigen();
  }

  hoehenPruefen() {
    if (!this.virtual || this.hoeheGeprueft) return;
    this.hoeheGeprueft = true;
    const balken = this.liste.querySelector(".perioden-balken");
    const zeile = this.liste.querySelector(".zeile");
    const bh = balken ? Math.ceil(balken.getBoundingClientRect().height) : 0;
    const zh = zeile ? Math.ceil(zeile.getBoundingClientRect().height) : 0;
    if ((bh > 8 && bh !== this.balkenH) || (zh > 8 && zh !== this.zeilenH)) {
      if (bh > 8) this.balkenH = bh;
      if (zh > 8) this.zeilenH = zh;
      this.slotsMitHoehe();
      if (this.fenster) this.fenster.style.height = `${this.listeHoehe}px`;
      this.fensterVon = -1;
      this.fensterBereichZeichnen(true);
    }
  }

  /** Baut die Slots mit den zuletzt gemessenen Zeilenhöhen neu, ohne die Schätzwerte zu überschreiben. */
  slotsMitHoehe() {
    const zeilenH = this.zeilenH;
    const balkenH = this.balkenH;
    const slots = [];
    let top = 0;
    const schieben = (typ, hoehe, extra) => {
      slots.push({ typ, top, hoehe, ...extra });
      top += hoehe;
    };
    this.jedenZeitraum((eintrag) => {
      if (eintrag.typ === "balken") {
        schieben("balken", balkenH, { slotId: `p:${eintrag.gruppe.schluessel}`, gruppe: eintrag.gruppe });
      } else schieben("zeile", zeilenH, { slotId: eintrag.buchung.id, buchung: eintrag.buchung });
    });
    this.slots = slots;
    this.listeHoehe = top;
    this.slotIndex = new Map(slots.map((s, i) => [s.slotId, i]));
  }

  slotZeigen(slotId, block = "nearest") {
    if (!this.virtual || !this.fenster) return false;
    const i = this.slotIndex.get(slotId);
    if (i === undefined) return false;
    const s = this.slots[i];
    const scroller = this.scrollBehaelter();
    const fenster = this.fenster.getBoundingClientRect();
    const sicht = scroller.getBoundingClientRect();
    const fensterTop = fenster.top - sicht.top + scroller.scrollTop;
    const pos = fensterTop + s.top;
    let ziel = scroller.scrollTop;
    if (block === "center") ziel = pos - (scroller.clientHeight - s.hoehe) / 2;
    else if (pos < scroller.scrollTop + 8) ziel = pos - 8;
    else if (pos + s.hoehe > scroller.scrollTop + scroller.clientHeight - 8) {
      ziel = pos - scroller.clientHeight + s.hoehe + 8;
    }
    ziel = Math.max(0, ziel);
    if (ziel !== scroller.scrollTop) scroller.scrollTop = ziel;
    this.fensterBereichZeichnen(false);
    return true;
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
      if (!kompakt) zelle.append(this.spaltenTrenner(feld, text));
      return zelle;
    }));
    this.zeilen = new Map();
    const fokusImGrid = this.liste.contains(document.activeElement) && document.activeElement.getAttribute("role") === "row";
    const editor = this.editorOffen;
    const editorFokus = editor ? editor.loesen() : false;
    this.slotsBauen();
    this.virtual = this.virtualAktiv();
    this.hoeheGeprueft = false;
    if (this.virtual) {
      this.fenster = h("div", { class: "listen-fenster" });
      this.fenster.style.height = `${this.listeHoehe}px`;
      this.fensterInnen = h("div", { class: "listen-fenster-innen" });
      this.fenster.append(this.fensterInnen);
      this.fensterVon = -1;
      this.liste.replaceChildren(kopf, this.fenster);
      this.scrollLauschen();
      this.fensterBereichZeichnen(true);
      requestAnimationFrame(() => this.hoehenPruefen());
    } else {
      const zeilen = [];
      this.jedenZeitraum((eintrag) => {
        zeilen.push(eintrag.typ === "balken" ? this.periodenBalken(eintrag.gruppe) : this.zeile(eintrag.buchung, kompakt));
      });
      this.liste.replaceChildren(kopf, ...zeilen);
    }
    this.gruppierungKnopfZustand();
    this.breitenAnwenden();
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
    const empfName = b.empfaenger ? nameAnzeige(b.empfaenger.name) : "";
    const empf = h("div", { role: "gridcell", class: "zelle zelle-empfaenger", "data-feld": "empfaenger",
      "data-empfaenger-id": b.empfaenger ? String(b.empfaenger.id) : "" },
    empfName ? markiert(empfName, b.markierungen, "empfänger")
      : (kompakt ? h("span", { class: "ersatz" }, markiert(b.verwendungszweck, b.markierungen, "verwendungszweck")) : ""));
    const zweckZelle = h("div", { role: "gridcell", class: "zelle zelle-verwendungszweck", "data-feld": "verwendungszweck" },
      markiert(b.verwendungszweck, b.markierungen, "verwendungszweck"));
    const belegMarke = b.belege && b.belege.length ? h("button", { type: "button", class: "beleg-marke", tid: `beleg-marke-${b.id}`,
        "data-nicht-ziehen": "", "data-anzahl": String(b.belege.length), tabindex: "-1",
        title: b.belege.map((d) => d.dateiname).join("\n"), "aria-label": `${b.belege.length} Dokument(e) ansehen`,
        onclick: (e) => { e.stopPropagation(); betrachter(b.belege, 0, e.currentTarget); } },
      "📎", b.belege.length > 1 ? String(b.belege.length) : "") : null;
    // mobil ist die Spalte Verwendungszweck ausgeblendet: Marke dann beim Empfänger
    if (belegMarke) {
      const zelle = kompakt ? empf : zweckZelle;
      // Text kürzen, Marke bleibt am Zellenende sichtbar und anklickbar
      zelle.replaceChildren(h("span", { class: "zelle-text" }, ...zelle.childNodes), belegMarke);
      zelle.classList.add("mit-marke");
    }
    const zeile = h("div", { role: "row", tid: `buchung-${b.id}`, class: "zeile", "aria-selected": "false",
      tabindex: "-1", "data-id": String(b.id), "data-status": b.status, "data-vorschlag": b.vorschlag ? "ja" : "nein" },
    datumEl("div", b.datum, { role: "gridcell", class: "zelle zelle-datum", "data-feld": "datum" }),
    empf,
    zweckZelle,
    kat,
    this.istKategorie ? kontoZelle(b) : null,
    h("div", { role: "gridcell", class: "zelle zelle-tags", "data-feld": "tags" },
      b.tags.map((t) => {
        const person = t.name === "Torsten" || t.name === "Tina";
        return h("span", { class: person ? "tag tag-person" : "tag", tid: "tag", "data-tag-id": String(t.id),
          "data-person": person ? t.name : null, title: person ? `Bestätigt von ${t.name}` : t.name }, t.name);
      }),
      b.verdacht ? h("span", { class: "tag tag-verdacht", tid: "verdacht", "data-grund": b.verdacht.grund,
        title: b.verdacht.text, "aria-label": b.verdacht.text }, "Verdächtig") : null),
    h("div", { role: "gridcell", class: "zelle zelle-status", "data-feld": "status" }, STATUS_TEXT[b.status] || b.status),
    betragEl("div", b.betrag, { role: "gridcell", class: "zelle zelle-betrag", "data-feld": "betrag" }));
    const bestaetigtVon = b.tags.filter((t) => t.name === "Torsten" || t.name === "Tina").map((t) => t.name);
    if (bestaetigtVon.length) zeile.dataset.bestaetigt = bestaetigtVon.join(" ");
    if (b.verdacht) zeile.dataset.verdacht = b.verdacht.grund;
    if (b.abgestimmt || b.status === "abgeglichen") zeile.dataset.gesperrt = "ja";
    const mark = markierung(b);
    if (mark) zeile.dataset.markierung = mark;
    const hinweise = [];
    if (this.mailBestaetigt.has(b.id)) {
      zeile.dataset.mail = "ja";
      hinweise.push(`durch Mail bestätigt: ${this.mailBestaetigt.get(b.id)}`);
    }
    if (hinweise.length) empf.title = [empfName, ...hinweise].filter(Boolean).join(" – ");
    this.zeilen.set(b.id, zeile);
    return zeile;
  }

  // ---------------------------------------------------------------- Spaltenbreiten (D-130)
  spaltenTrenner(feld, text) {
    const t = h("span", { class: "spalten-trenner", tid: `spalte-trenner-${feld}`, role: "separator",
      "aria-orientation": "vertical", "aria-label": `Breite der Spalte ${text}`, "data-nicht-ziehen": "",
      title: "Ziehen ändert die Breite, Doppelklick passt sie an den Inhalt an" });
    t.addEventListener("click", (e) => e.stopPropagation());
    t.addEventListener("dblclick", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.spalteAnpassen([feld]);
    });
    t.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      this.breitenFestlegen();
      const start = this.breiten[feld];
      const x0 = e.clientX;
      t.setPointerCapture(e.pointerId);
      t.classList.add("aktiv");
      const bewegen = (ev) => {
        this.breiten[feld] = spalteBegrenzen(start + ev.clientX - x0);
        this.breitenAnwenden();
      };
      const ende = () => {
        t.removeEventListener("pointermove", bewegen);
        t.removeEventListener("pointerup", ende);
        t.removeEventListener("pointercancel", ende);
        t.classList.remove("aktiv");
        spaltenSpeichern(this.spaltenVariante, this.breiten);
      };
      t.addEventListener("pointermove", bewegen);
      t.addEventListener("pointerup", ende);
      t.addEventListener("pointercancel", ende);
    });
    return t;
  }

  /** Alle Spalten auf ihre aktuell gezeichnete Breite festlegen (vor dem ersten Ziehen oder Anpassen). */
  breitenFestlegen() {
    const kopf = this.liste.querySelector(".liste-kopf");
    for (const [feld] of this.spalten) {
      if (this.breiten[feld]) continue;
      const z = kopf && kopf.querySelector(`.zelle-${feld}`);
      this.breiten[feld] = spalteBegrenzen(z ? z.getBoundingClientRect().width : SPALTE_ERSATZ);
    }
  }

  breitenAnwenden() {
    const eigen = this.liste.dataset.kompakt !== "ja" && this.spalten.some(([f]) => this.breiten[f]);
    this.liste.classList.toggle("spalten-eigen", eigen);
    if (eigen) {
      this.liste.style.setProperty("--spalten",
        this.spalten.map(([f]) => `${this.breiten[f] || SPALTE_ERSATZ}px`).join(" "));
    } else this.liste.style.removeProperty("--spalten");
  }

  /** Doppelklick auf den Trenner (wie in Excel): Spalte so breit wie ihr breitester Inhalt (Kopf und geladene Zeilen). */
  spalteAnpassen(felder) {
    this.breitenFestlegen();
    const messer = h("div", { class: "spalten-messer", "aria-hidden": "true" });
    const klone = new Map();
    for (const feld of felder) {
      klone.set(feld, [...this.liste.querySelectorAll(`[role="row"] > .zelle-${feld}`)].map((z) => {
        const k = z.cloneNode(true);
        k.removeAttribute("data-testid");
        for (const x of k.querySelectorAll("[data-testid]")) x.removeAttribute("data-testid");
        messer.append(k);
        return k;
      }));
    }
    this.liste.append(messer);
    for (const [feld, liste] of klone) {
      const w = Math.max(0, ...liste.map((k) => k.getBoundingClientRect().width));
      if (w > 0) this.breiten[feld] = spalteBegrenzen(Math.ceil(w) + 2);
    }
    messer.remove();
    this.breitenAnwenden();
    spaltenSpeichern(this.spaltenVariante, this.breiten);
  }

  spaltenZuruecksetzen() {
    this.breiten = {};
    this.breitenAnwenden();
    spaltenSpeichern(this.spaltenVariante, this.breiten);
  }

  kopfMenue(e) {
    e.preventDefault();
    kontextmenue(e.clientX, e.clientY, [
      { tid: "km-spalten-anpassen", text: "Alle Spalten an den Inhalt anpassen",
        tun: () => this.spalteAnpassen(this.spalten.map(([f]) => f)) },
      { tid: "km-spalten-zuruecksetzen", text: "Spaltenbreiten zurücksetzen", aktiv: this.spalten.some(([f]) => this.breiten[f]),
        tun: () => this.spaltenZuruecksetzen() },
    ], null);
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
    this.auswahlModusZeigen(n);
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
    if (mitDom && this.virtual) this.slotZeigen(id);
    this.auswahlZeigen();
    const z = this.zeilen.get(id);
    if (z && mitDom) {
      // nur senkrecht nachführen: eine Zeile ist breiter als die Liste, waagerecht bleibt die Lage (23.2)
      const links = this.listenSpalte ? this.listenSpalte.scrollLeft : 0;
      z.focus({ preventScroll: true });
      if (!this.virtual) z.scrollIntoView({ block: "nearest" });
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
    const ids = this.sichtbareIds();
    const i = ids.indexOf(id);
    const strg = e.ctrlKey || e.metaKey;
    const seite = Math.max(1, Math.floor((this.listenSpalte.clientHeight || 400) / (z.offsetHeight || 32)) - 1);
    const ziel = { ArrowDown: ids[i + 1], ArrowUp: ids[i - 1], Home: ids[0], End: ids[ids.length - 1],
      PageDown: ids[Math.min(ids.length - 1, i + seite)], PageUp: ids[Math.max(0, i - seite)] }[e.key];
    if (["ArrowDown", "ArrowUp", "Home", "End", "PageDown", "PageUp"].includes(e.key)) {
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
    if (this.vortaste) { this.vortasteBeenden(); return true; }
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
    this.liste.addEventListener("keydown", (e) => this.taste(e));
    this.liste.addEventListener("contextmenu", (e) => {
      if (e.target.closest(".liste-kopf") && !oberflaeche.istMobil()) { this.kopfMenue(e); return; }
      const z = zeileVon(e.target);
      if (!z || e.target.closest("input, textarea")) return;
      e.preventDefault();
      // mobil (D-141): das vom Browser zur langen Berührung gemeldete Kontextmenü entfällt; sie startet die Auswahl
      if (oberflaeche.istMobil() && performance.now() - this.letzteBeruehrung < 2500) return;
      const id = Number(z.dataset.id);
      if (!this.auswahl.has(id)) { this.auswahl = new Set([id]); this.anker = id; }
      this.fokussieren(id);
      this.menue(e.clientX, e.clientY, z, e.altKey);
    });
    // Dateien aus dem Betriebssystem auf eine Zeile ziehen (D-123): gewählte Zeile → alle gewählten Buchungen
    ablageEinrichten(this.liste, (z) => {
      const id = Number(z.dataset.id);
      return this.auswahl.has(id) && this.auswahl.size > 1 ? this.auswahlIds() : [id];
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
      if (oberflaeche.istMobil()) { this.auswahlStarten(id); return; }
      if (!this.auswahl.has(id)) { this.auswahl = new Set([id]); this.anker = id; }
      this.fokussieren(id, false);
      this.menue(x, y, z);
    });
    let w = null;
    this.letzteBeruehrung = -Infinity;
    this.liste.addEventListener("touchstart", (e) => {
      this.letzteBeruehrung = performance.now();
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
      const dy = Math.abs(w.ey - w.y);
      if (w.richtung === undefined && (dx > 10 || dy > 10)) w.richtung = dx > dy ? "waagerecht" : "senkrecht";
      if (dx > 10 && dx > dy && e.cancelable) e.preventDefault();
      // mobil (D-141): die Zeile folgt dem Finger und zeigt, was beim Loslassen geschieht
      if (w.richtung === "waagerecht" && oberflaeche.istMobil()) this.wischZeigen(w.z, w.ex - w.x, dy);
    }, { passive: false });
    this.liste.addEventListener("touchcancel", () => { if (w) this.wischEnde(w.z); w = null; });
    this.liste.addEventListener("touchend", (e) => {
      if (!w || w.ex === undefined) { w = null; return; }
      const dx = w.ex - w.x;
      const dy = Math.abs(w.ey - w.y);
      const dt = performance.now() - w.t;
      const z = w.z;
      w = null;
      this.wischEnde(z);
      // mobil zeigt die Zeile den Zustand an: dort zählt nur der Weg, nicht die Dauer (D-141)
      if (Math.abs(dx) < WISCH_WEG || dy > WISCH_QUER || (dt > 1000 && !oberflaeche.istMobil())) return;
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

  // ---------------------------------------------------------------- Rückmeldung beim Wischen (D-141)
  wischZeigen(z, dx, dy) {
    if (dy > WISCH_QUER) { this.wischEnde(z); return; }
    if (!this.wischHinweis) {
      this.wischHinweis = h("div", { class: "wisch-hinweis", "aria-hidden": "true" },
        h("span", { class: "wisch-links" }), h("span", { class: "wisch-rechts" }, "Kategorie …"));
    }
    const hw = this.wischHinweis;
    if (hw.parentNode !== this.listenSpalte) this.listenSpalte.append(hw);
    const id = Number(z.dataset.id);
    hw.firstChild.textContent = this.auswahl.has(id) ? "✕ Abwählen" : "✓ Auswählen";
    hw.style.top = z.offsetTop + "px";
    hw.style.height = z.offsetHeight + "px";
    hw.dataset.richtung = dx > 0 ? "rechts" : "links";
    hw.dataset.bereit = Math.abs(dx) >= WISCH_WEG ? "ja" : "nein";
    hw.hidden = false;
    z.classList.add("wischt");
    const weg = Math.sign(dx) * Math.min(Math.abs(dx), 160);
    z.style.transform = `translateX(${weg}px)`;
  }

  wischEnde(z) {
    if (this.wischHinweis) this.wischHinweis.hidden = true;
    if (!z || !z.classList.contains("wischt")) return;
    z.classList.remove("wischt");
    z.style.transform = "";
  }

  // ---------------------------------------------------------------- Bestätigung durch Torsten oder Tina (D-155)
  bestaetigt(b, name) { return !!(b && b.tags.some((t) => t.name === name)); }

  bestaetigenEintrag(ids) {
    const name = personLesen();
    if (!name || !ids.length) return null;
    const alle = ids.every((id) => this.bestaetigt(this.eintraege.find((x) => x.id === id), name));
    return { tid: "km-bestaetigen", kuerzel: "b", text: alle ? `Bestätigung von ${name} zurücknehmen` : `Als ${name} bestätigen`,
      tun: () => this.personMarkieren(ids, !alle) };
  }

  bestaetigungZeile(b) {
    const name = personLesen();
    const namen = b.tags.filter((t) => t.name === "Torsten" || t.name === "Tina").map((t) => t.name);
    const hat = name && this.bestaetigt(b, name);
    return h("p", { class: "bestaetigung", tid: "buchung-bestaetigung" },
      namen.length ? ["Bestätigt von ", namen.join(" und "), ". "] : "Noch von niemandem bestätigt. ",
      name ? knopf(hat ? `Bestätigung von ${name} zurücknehmen` : `Als ${name} bestätigen`, {
        tid: "buchung-bestaetigen", class: "knopf knopf-klein",
        onclick: () => this.personMarkieren([b.id], !hat) }) : "Oben rechts wählen, wer du bist.");
  }

  async personMarkieren(ids, hinzu) {
    const name = personLesen();
    if (!name) { melde("hinweis", "Bitte oben rechts wählen, wer du bist."); return; }
    try {
      await aktion(async () => {
        let t = stamm.tags.find((x) => x.name === name);
        if (!t && hinzu) t = await api("POST", "/api/tags", { name });
        if (!t) return null;
        await api("POST", "/api/buchungen/mehrfach/tags", {
          buchung_ids: ids, hinzufuegen: hinzu ? [t.id] : [], entfernen: hinzu ? [] : [t.id] });
        // Importiert wird durch die Bestätigung der Person zu Bestätigt (D-159).
        if (hinzu) {
          const offen = ids.filter((id) => {
            const x = this.eintraege.find((e) => e.id === id);
            return x && x.status === "importiert";
          }).sort((a, c) => a - c);
          if (offen.length) await api("POST", "/api/buchungen/mehrfach/aendern", { buchung_ids: offen, status: "bestaetigt" });
        }
        return true;
      }, { erfolg: hinzu ? `Als ${name} bestätigt.` : `Bestätigung von ${name} zurückgenommen.` });
    } catch { /* gemeldet */ }
  }

  // ---------------------------------------------------------------- Tastaturkürzel (D-167)
  /** Taste außerhalb von Textfeldern und Dialogen; true, wenn sie hier eine Wirkung hatte. */
  kuerzel(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    if (document.activeElement && document.activeElement.closest(".baum, .kontextmenue")) return false;
    const vor = this.vortaste || "";
    if (vor) this.vortasteBeenden();
    if (!vor && VORTASTEN[e.key]) { this.vortasteStarten(e.key); return true; }
    const k = KUERZEL.find(([v, taste]) => v === vor && taste === e.key);
    if (!k) {
      if (vor && !["Shift", "CapsLock"].includes(e.key)) melde("hinweis", `„${vor} ${e.key}“ ist nicht belegt.`);
      if (vor && ["Shift", "CapsLock"].includes(e.key)) this.vortasteStarten(vor);   // Umschalt allein bricht nicht ab
      return !!vor;
    }
    Promise.resolve().then(() => k[3](this)).catch(() => { /* gemeldet */ });
    return true;
  }

  /** Kürzel Nummer i aus der Befehlspalette ausführen. */
  kuerzelAusfuehren(i) {
    const k = KUERZEL[i];
    if (k) Promise.resolve().then(() => k[3](this)).catch(() => { /* gemeldet */ });
  }

  vortasteStarten(vor) {
    this.vortaste = vor;
    if (!this.vortasteEl) {
      this.vortasteEl = h("div", { class: "kuerzel-hinweis", tid: "kuerzel-hinweis", role: "status", "aria-live": "polite" });
    }
    const el = this.vortasteEl;
    el.dataset.vortaste = vor;
    el.replaceChildren(h("strong", null, `${VORTASTEN[vor]} (${vor}) – weiter mit:`),
      h("ul", null, KUERZEL.filter(([v]) => v === vor).map(([, taste, text]) => h("li", null, h("kbd", null, taste), " ", text))),
      h("span", { class: "klein" }, "Esc bricht ab"));
    document.body.append(el);
  }

  vortasteBeenden() {
    this.vortaste = "";
    if (this.vortasteEl) this.vortasteEl.remove();
  }

  /** Markierte Buchungen, sonst die mit dem Fokus (wird dann markiert). */
  mitZielen(wirkung) {
    if (!this.auswahl.size && this.fokusId !== null && this.eintraege.some((b) => b.id === this.fokusId)) {
      this.auswahl.add(this.fokusId);
      this.anker = this.fokusId;
      this.auswahlZeigen();
    }
    const ids = this.auswahlIds();
    if (!ids.length) { melde("hinweis", "Keine Buchung markiert."); return undefined; }
    const el = this.zeilen.get(this.fokusId) || this.zeilen.get(ids[0]) || this.liste;
    return wirkung(ids, el);
  }

  einzeln(ids, wirkung) {
    if (ids.length !== 1) { melde("hinweis", "Dafür genau eine Buchung markieren."); return undefined; }
    return wirkung(this.eintraege.find((b) => b.id === ids[0]));
  }

  vorschlagTaste(ids, was) {
    const mit = ids.filter((id) => (this.eintraege.find((b) => b.id === id) || {}).vorschlag);
    if (!mit.length) { melde("hinweis", "Die markierten Buchungen haben keinen Vorschlag."); return undefined; }
    return this.vorschlag(null, ids, was);
  }

  /** Offener Verdacht, sonst bei genau zwei Buchungen ein neues Paar (D-165). */
  dubletteFuer(ids) {
    const verdacht = this.dublettenVerdacht(ids);
    const paar = ids.length === 2 && !verdacht ? {
      id: null, buchung_id: ids[0], kandidat_ids: [ids[1]], grund: "manuell", status: "offen", vorschlag: true,
    } : null;
    return verdacht || paar;
  }

  filterLeisteNeu() {
    const neu = this.filterAufbauen();
    neu.hidden = !this.filterSichtbar;
    this.filterLeiste.replaceWith(neu);
    this.filterLeiste = neu;
  }

  filterLeisteTaste() {
    this.filterUmschalten();
    if (this.filterSichtbar) this.filterFokus("bk-0-feld");
    else this.listeFokussieren();
  }

  filterFokus(testid) {
    if (!this.filterSichtbar) this.filterUmschalten();
    const el = tid(testid, this.filterLeiste);
    if (el) el.focus();
  }

  listeFokussieren() {
    const id = this.fokusId ?? this.sichtbareIds()[0];
    if (id !== undefined && id !== null) this.fokussieren(id);
    else this.liste.focus();
  }

  filterWieBuchung(testid) {
    const ids = this.auswahl.size ? this.auswahlIds() : (this.fokusId !== null ? [this.fokusId] : []);
    if (ids.length !== 1) { melde("hinweis", "Dafür genau eine Buchung markieren."); return undefined; }
    const b = this.eintraege.find((x) => x.id === ids[0]);
    const e = this.filterEintrag(b).kinder.find((k) => k.tid === testid);
    if (!e || e.aktiv === false) { melde("hinweis", "Die Buchung hat keinen Empfänger."); return undefined; }
    return e.tun();
  }

  sortierungWechseln(umkehren) {
    const sort = this.sortierung;
    const ab = sort.startsWith("-");
    const feld = sort.replace(/^-/, "");
    if (umkehren) return this.filterSetzen("sortierung", ab ? feld : "-" + feld);
    const felder = this.spalten.filter(([, , sortierbar]) => sortierbar).map(([f]) => f);
    const neu = felder[(felder.indexOf(feld) + 1) % felder.length];
    melde("hinweis", `Sortiert nach ${this.spalten.find(([f]) => f === neu)[1]}.`);
    return this.filterSetzen("sortierung", (ab ? "-" : "") + neu);
  }

  panelUmschalten(p) {
    if (oberflaeche.istMobil()) return;
    const l = this.layout.panels[p];
    l.eingeklappt = !l.eingeklappt;
    this.layoutAnwenden();
    if (p === "details" && !l.eingeklappt) this.detailsZeichnen();
  }

  // ---------------------------------------------------------------- Kontextmenü (8.2)
  auswahlIds() { return this.ids().filter((x) => this.auswahl.has(x)); }

  /** Filter aus der gewählten Buchung. Gleich ist derselbe Empfänger bzw. derselbe Text,
   * ähnlich ein gemeinsamer Namensanfang oder ein gemeinsames Wort (D-158). */
  filterEintrag(b) {
    const zweck = b ? b.verwendungszweck : "";
    const aehnlich = zweck
      ? { zweck_aehnlich: zweck, zweck_gleich: "", zweck_leer: "", verwendungszweck: "" }
      : { zweck_leer: "true", zweck_gleich: "", zweck_aehnlich: "", verwendungszweck: "" };
    return { tid: "km-filter", text: "Filter", aktiv: !!b, kinder: [
      { tid: "km-filter-empfaenger", text: "gleicher Empfänger", aktiv: !!(b && b.empfaenger),
        tun: () => this.ausdruckSetzen(this.mitTeil(/^(?:empf|empfänger|empfaenger)\s*==/, `empf == ${qText(b.empfaenger.name)}`)) },
      { tid: "km-filter-zweck", text: "Gleicher Verwendungszweck",
        tun: () => this.ausdruckSetzen(this.mitTeil(/^(?:vwz|verwendungszweck)\s*==/, `vwz == ${qText(zweck)}`)) },
      { tid: "km-filter-zweck-aehnlich", text: "ähnlicher Verwendungszweck", tun: () => this.filterAnwenden(aehnlich) },
      { tid: "km-filter-empfaenger-aehnlich", text: "ähnlicher Empfänger", aktiv: !!(b && b.empfaenger),
        tun: () => this.filterAnwenden({ empfaenger_aehnlich: b.empfaenger.name, empfaenger_id: "", ohne_empfaenger: "" }) },
    ] };
  }

  async filterAnwenden(teil) {
    const neu = { ...this.filter };
    for (const [k, v] of Object.entries(teil)) {
      if (v === null || v === undefined || v === "") delete neu[k];
      else neu[k] = v;
    }
    this.filter = neu;
    this.auswahl.clear();
    this.anker = null;
    this.seiten = 1;
    this.urlSchreiben();
    const leiste = this.filterAufbauen();   // bleibt eingeklappt; die Zusammenfassung nennt den Filter (D-188)
    leiste.hidden = !this.filterSichtbar;
    this.filterLeiste.replaceWith(leiste);
    this.filterLeiste = leiste;
    await this.laden();
  }

  /** Offener Dublettenverdacht: eine Buchung wie bisher, oder genau das gewählte Paar. */
  dublettenVerdacht(ids) {
    if (ids.length === 1) {
      const id = ids[0];
      return this.verdachte.find((v) => v.buchung_id === id || v.kandidat_ids.includes(id)) || null;
    }
    if (ids.length === 2) {
      return this.verdachte.find((v) => {
        const alle = [v.buchung_id, ...v.kandidat_ids];
        return alle.length === 2 && alle.includes(ids[0]) && alle.includes(ids[1]);
      }) || null;
    }
    return null;
  }

  menue(x, y, ausloeser, alt = false) {
    const ids = this.auswahlIds();
    const eine = ids.length === 1;
    const mitVorschlag = this.eintraege.some((b) => this.auswahl.has(b.id) && b.vorschlag);
    const dublette = this.dubletteFuer(ids);
    const b = eine ? this.eintraege.find((x2) => x2.id === ids[0]) : null;
    kontextmenue(x, y, [
      { tid: "km-kategorie", kuerzel: "k", text: "Kategorie setzen…", tun: () => this.kategorieWaehlen(ids, ausloeser) },
      { tid: "km-tags", kuerzel: "t", text: "Tags…", tun: () => tagAuswahl(ids, ausloeser) },
      { tid: "km-splitten", kuerzel: "x", text: "Splitten…", aktiv: eine, tun: () => splitDialog(b, ausloeser) },
      { tid: "km-dublette", kuerzel: "d", text: "Als Dublette markieren…", aktiv: !!dublette,
        tun: () => { if (dublette) dubletteDialog(dublette, ausloeser); } },
      { tid: "km-vorschlag-annehmen", kuerzel: "a", text: "Vorschlag annehmen", aktiv: mitVorschlag, tun: () => this.vorschlag(null, ids, "annehmen") },
      { tid: "km-vorschlag-ablehnen", kuerzel: "⇧A", text: "Vorschlag ablehnen", aktiv: mitVorschlag, tun: () => this.vorschlag(null, ids, "ablehnen") },
      { tid: "km-bearbeiten", kuerzel: "F2", text: "Verwendungszweck bearbeiten", aktiv: eine, tun: () => this.bearbeiten(ids[0], "verwendungszweck") },
      { tid: "km-status", kuerzel: "s", text: "Status setzen…", tun: () => this.statusWaehlen(ids, ausloeser) },
      this.bestaetigenEintrag(ids),
      this.filterEintrag(b),
      { tid: "km-mehrfach", kuerzel: "e", text: "Bearbeiten…", tun: () => this.mehrfachDialog(ids, ausloeser) },
      this.gegenbuchungEintrag(b, x, y, ausloeser),
      // Dokumente (D-123): an alle gewählten Buchungen
      { tid: "km-dokument-anhaengen", kuerzel: "m", text: "Dokument anhängen…", tun: () => dateiWaehlen(ids) },
      oberflaeche.istMobil() ? { tid: "km-dokument-foto", text: "Foto aufnehmen…", tun: () => dateiWaehlen(ids, { kamera: true }) } : null,
      { tid: "km-dokument-mail", kuerzel: "⇧M", text: "E-Mail anhängen…", tun: () => mailDialog(ids, ausloeser) },
      { tid: "km-dokumente-ansehen", text: "Dokumente ansehen", aktiv: !!(b && b.belege && b.belege.length),
        tun: () => betrachter(b.belege, 0, ausloeser) },
      // Verschieben nur mit gehaltener Alt-Taste, auf dem Handy im Menü (D-160)
      ...(!this.istKategorie && (alt || oberflaeche.istMobil()) ? [{ tid: "km-verschieben",
        text: "Auf anderes Konto verschieben…", tun: () => this.verschiebenDialog(ids, ausloeser) }] : []),
      { tid: "km-loeschen", kuerzel: "Entf", text: "Löschen…", tun: () => this.loeschen(ausloeser) },
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
    return { tid: "km-gegenbuchung", kuerzel: "g", text: mehrere ? "Gehe zur Gegenbuchung…" : "Gehe zur Gegenbuchung",
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
    if (this.virtual) this.slotZeigen(id, "center");
    this.fokussieren(id);
    const z = this.zeilen.get(id);
    if (!z) return;
    const links = this.listenSpalte ? this.listenSpalte.scrollLeft : 0;
    if (!this.virtual) z.scrollIntoView({ block: "center" });
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
    this.istKategorie ? null : knopf("Verschieben…", { tid: "mehrfach-verschieben", class: "knopf nur-mobil",
      onclick: (e) => this.verschiebenDialog(this.auswahlIds(), e.currentTarget) }),
    k("mehrfach-loeschen", "Löschen…", (el) => this.loeschen(el)),
    k("auswahl-aufheben", "Auswahl aufheben", () => { this.auswahl.clear(); this.auswahlZeigen(); }),
    // mobil (D-141): alle übrigen Aktionen über das Kontextmenü der Auswahl
    knopf("Mehr", { tid: "mehrfach-mehr", class: "knopf nur-mobil", "aria-haspopup": "menu",
      onclick: (e) => { const el = e.currentTarget; const [x, y] = menuePosition(null, el); this.menue(x, y, el); } }));
  }

  // ---------------------------------------------------------------- Auswahlmodus mobil (D-141)
  auswahlKopfAufbauen() {
    this.auswahlKopfText = h("span", { class: "auswahl-kopf-text", tid: "auswahl-kopf-anzahl", "aria-live": "polite" });
    return h("div", { class: "auswahl-kopf", tid: "auswahl-kopf", role: "toolbar", "aria-label": "Auswahlmodus", hidden: true },
      h("button", { type: "button", class: "knopf-flach auswahl-beenden", tid: "auswahl-beenden", "aria-label": "Auswahl beenden",
        onclick: () => { this.auswahl.clear(); this.auswahlZeigen(); } }, "✕"),
      this.auswahlKopfText,
      knopf("Alle", { tid: "auswahl-alle", class: "knopf knopf-flach", "aria-label": "Alle geladenen Buchungen auswählen",
        onclick: () => { this.auswahl = new Set(this.ids()); this.auswahlZeigen(); } }));
  }

  /** Lange Berührung (mobil): Auswahlmodus mit dieser Zeile beginnen bzw. die Zeile hinzunehmen. */
  auswahlStarten(id) {
    this.auswahl.add(id);
    this.anker = id;
    try { if (navigator.vibrate) navigator.vibrate(12); } catch (e) { /* ohne Vibration */ }
    this.fokussieren(id, false);
  }

  /** Mobil sichtbarer Auswahlmodus: Häkchen an den Zeilen, Kopfleiste mit Anzahl; Zurück-Taste beendet ihn. */
  auswahlModusZeigen(n) {
    const an = oberflaeche.istMobil() && n > 0;
    if (this.liste.dataset.auswahlmodus !== undefined || an) this.liste.dataset.auswahlmodus = an ? "ja" : "nein";
    if (this.auswahlKopf) {
      if (an) {
        // direkt unter der Kopfzeile der App (Rückgängig bleibt erreichbar), über dem Seitenkopf
        this.auswahlKopf.style.top = Math.max(0, tid("app-kopf").getBoundingClientRect().bottom) + "px";
      }
      this.auswahlKopf.hidden = !an;
      this.auswahlKopfText.textContent = n === 1 ? "1 ausgewählt" : `${n} ausgewählt`;
    }
    if (an && !this.zurueckEintrag) {
      try { history.pushState({ kontorAuswahl: true }, "", location.href); this.zurueckEintrag = true; } catch (e) { /* ohne */ }
    } else if (!an && this.zurueckEintrag) {
      this.zurueckEintrag = false;
      if (history.state && history.state.kontorAuswahl) { this.zurueckIgnorieren = true; history.back(); }
    }
  }

  /** Zurück-Taste (popstate): true, wenn sie hier verbraucht wurde (Auswahl beendet). */
  zurueck() {
    if (this.zurueckIgnorieren) { this.zurueckIgnorieren = false; return true; }
    if (!this.zurueckEintrag) return false;
    this.zurueckEintrag = false;
    this.auswahl.clear();
    this.auswahlZeigen();
    return true;
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
