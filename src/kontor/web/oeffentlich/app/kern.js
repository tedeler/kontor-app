/* Kontor – Kern der Oberfläche (oberflaeche.md): DOM-Hilfen, REST-Zugriff, Darstellung von Werten,
 * Stammdaten, Meldungen, Ebenen (Dialoge/Menüs) und Rückgängig über das Änderungsprotokoll (11, E-142).
 * Beträge sind ganze Cent; Umrechnungen nur mit Ganzzahlarithmetik. Texte aus dem Buchbestand werden
 * ausschließlich als Text gesetzt (textContent/Attribute), nie als HTML.
 */

// ------------------------------------------------------------------ DOM
export function h(tag, attrs, ...kinder) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "tid") el.dataset.testid = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (k === "value") el.value = v;
      else if (k === "checked") el.checked = !!v;
      else if (k === "selected") el.selected = !!v;
      else if (k === "stil") { for (const [p, w] of Object.entries(v)) el.style.setProperty(p, w); }
      else el.setAttribute(k, v === true ? "" : String(v));
    }
  }
  anhaengen(el, kinder);
  return el;
}

export function anhaengen(el, kinder) {
  for (const kind of [kinder].flat(Infinity)) {
    if (kind === null || kind === undefined || kind === false) continue;
    el.append(kind instanceof Node ? kind : document.createTextNode(String(kind)));
  }
  return el;
}

export const $ = (sel, wurzel) => (wurzel || document).querySelector(sel);
export const tid = (x, wurzel) => (wurzel || document).querySelector(`[data-testid="${x}"]`);

let zaehler = 0;
export const neueId = (praefix) => `${praefix}-${++zaehler}`;

export function istTexteingabe(el) {
  if (!el || !el.tagName) return false;
  if (el.isContentEditable) return true;
  const t = el.tagName;
  if (t === "TEXTAREA" || t === "SELECT") return true;
  if (t !== "INPUT") return false;
  return !["checkbox", "radio", "button", "submit", "reset", "file", "range", "color"].includes(el.type);
}

// ------------------------------------------------------------------ Werte (5)
const NBSP = " ";

/** Cent → „-1.234,56 €“ wie Intl.NumberFormat("de-DE", EUR), nur mit Ganzzahlen. */
export function betragText(cent) {
  if (cent === null || cent === undefined) return "";
  const neg = cent < 0;
  const abs = Math.abs(cent);
  const euro = Math.trunc(abs / 100);
  const rest = abs % 100;
  const gruppen = String(euro).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return (neg ? "-" : "") + gruppen + "," + String(rest).padStart(2, "0") + NBSP + "€";
}

/** Betragseingabe „[-]Ziffern[,Ziffern]“ (Tausenderpunkte erlaubt) → Cent; ungültig → null, leer → "". */
export function betragLesen(text) {
  const s = String(text ?? "").trim();
  if (s === "") return "";
  const m = /^(-?)(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?$/.exec(s);
  if (!m) return null;
  const cent = Number(m[2].replace(/\./g, "")) * 100 + Number((m[3] || "0").padEnd(2, "0"));
  if (!Number.isSafeInteger(cent)) return null;
  return m[1] ? -cent : cent;
}

/** Cent → Eingabetext „-12,34“ (ohne Tausenderpunkte). */
export function betragEingabe(cent) {
  if (cent === null || cent === undefined || cent === "") return "";
  const neg = cent < 0;
  const abs = Math.abs(cent);
  return (neg ? "-" : "") + Math.trunc(abs / 100) + "," + String(abs % 100).padStart(2, "0");
}

export function betragEl(tag, cent, attrs) {
  const klasse = (attrs && attrs.class ? attrs.class + " " : "") + "betrag" + (cent < 0 ? " negativ" : "");
  return h(tag, { ...(attrs || {}), class: klasse, "data-betrag": String(cent) }, betragText(cent));
}

export function datumText(iso) {
  if (!iso) return "";
  const [j, m, t] = iso.slice(0, 10).split("-");
  return `${t}.${m}.${j}`;
}

export function datumEl(tag, iso, attrs) {
  return h(tag, { ...(attrs || {}), "data-datum": iso ? iso.slice(0, 10) : "" }, datumText(iso));
}

const zwei = (n) => String(n).padStart(2, "0");

export function zeitText(wert) {
  if (!wert) return "";
  const d = new Date(wert);
  if (Number.isNaN(d.getTime())) return wert;
  return `${zwei(d.getDate())}.${zwei(d.getMonth() + 1)}.${d.getFullYear()} ${zwei(d.getHours())}:${zwei(d.getMinutes())}`;
}

export function zeitEl(tag, wert, attrs) {
  return h(tag, { ...(attrs || {}), "data-zeitpunkt": wert || "" }, zeitText(wert));
}

export const STATUS_TEXT = { importiert: "Importiert", vorlaeufig: "Vorläufig", bestaetigt: "Bestätigt",
  abgeglichen: "Abgeglichen" };
export const ART_TEXT = { girokonto: "Girokonto", sparkonto: "Sparkonto", kreditkonto: "Kreditkonto",
  aufwand: "Ausgaben", ertrag: "Einnahmen", eigenkapital: "Eigenkapital" };
export const BESTAND = new Set(["girokonto", "sparkonto", "kreditkonto"]);

/** Normalisierung für Befehlspalette und Kategorie-Auswahl (12.3). */
export function normalisieren(text) {
  return String(text)
    .replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue")
    .replace(/Ä/g, "Ae").replace(/Ö/g, "Oe").replace(/Ü/g, "Ue")
    .replace(/ß/g, "ss").replace(/ẞ/g, "SS")
    .normalize("NFKD").replace(/\p{M}/gu, "")
    .toLowerCase();
}

export function passt(eingabe, beschriftung) {
  const woerter = normalisieren(eingabe).split(/\s+/).filter(Boolean);
  const ziel = normalisieren(beschriftung);
  return woerter.every((w) => ziel.includes(w));
}

export const nachName = (a, b) => a.name.localeCompare(b.name, "de");

// ------------------------------------------------------------------ REST (1 Nr. 2, 19)
export class ApiFehler extends Error {
  constructor(status, fehler) {
    super(fehler && fehler.meldung ? fehler.meldung : `Die Anfrage ist fehlgeschlagen (HTTP ${status}).`);
    this.status = status;
    this.code = fehler ? fehler.code : "unbekannt";
    this.details = fehler ? fehler.details : null;
  }
}

export class OfflineFehler extends Error {
  constructor() { super("Keine Verbindung zum Server (offline)."); this.offline = true; }
}

export const anmeldung = { aktiv: false, csrf: null, geladen: false };
const offlineBeobachter = [];
export const beiOffline = (f) => offlineBeobachter.push(f);

export async function anmeldungLaden() {
  const r = await fetchSicher("/api/anmeldung", { cache: "no-store", credentials: "same-origin" });
  const d = await r.json();
  anmeldung.aktiv = !!d.aktiv;
  anmeldung.csrf = d.csrf_token || null;
  anmeldung.geladen = true;
  if (d.aktiv && !d.angemeldet) zurAnmeldung();
  return d;
}

export function zurAnmeldung() {
  const hier = location.pathname + location.search;
  // kodiert wie sicherheit.md 3.2: alles außer A–Z a–z 0–9 - . _ ~ / prozentkodiert (oberflaeche.md 19)
  const weiter = encodeURIComponent(hier.startsWith("/") ? hier : "/").replace(/%2F/g, "/")
    .replace(/[!'()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());
  location.assign("/anmelden?weiter=" + weiter);
}

async function fetchSicher(pfad, opt) {
  try {
    return await fetch(pfad, opt);
  } catch (e) {
    for (const f of offlineBeobachter) f();
    throw new OfflineFehler();
  }
}

/** REST-Aufruf; schreibende Anfragen tragen bei aktiver Anmeldung X-Kontor-CSRF (sicherheit.md 4.6). */
export async function api(methode, pfad, koerper, optionen) {
  const o = optionen || {};
  for (let versuch = 0; ; versuch++) {
    const opt = { method: methode, headers: {}, credentials: "same-origin", cache: "no-store" };
    if (o.formular) opt.body = o.formular;
    else if (koerper !== undefined) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(koerper);
    }
    if (anmeldung.csrf && methode !== "GET" && methode !== "HEAD") opt.headers["X-Kontor-CSRF"] = anmeldung.csrf;
    const r = await fetchSicher(pfad, opt);
    if (r.status === 401 && !pfad.startsWith("/api/anmeldung")) {
      zurAnmeldung();
      throw new ApiFehler(401, { code: "nicht_angemeldet", meldung: "Die Sitzung ist abgelaufen. Bitte neu anmelden." });
    }
    if (o.roh) {
      if (!r.ok) throw new ApiFehler(r.status, await fehlerLesen(r));
      return r;
    }
    if (r.status === 204) return null;
    let daten = null;
    try { daten = await r.json(); } catch (e) { daten = null; }
    if (r.status === 403 && daten && daten.fehler && daten.fehler.code === "csrf_ungueltig" && versuch === 0) {
      await anmeldungLaden();          // 19: Status einmal neu lesen, Anfrage einmal wiederholen
      continue;
    }
    if (!r.ok) throw new ApiFehler(r.status, daten && daten.fehler);
    return daten;
  }
}

async function fehlerLesen(r) {
  try { return (await r.json()).fehler; } catch (e) { return null; }
}

export function abfrage(params) {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.append(k, v === true ? "true" : v === false ? "false" : String(v));
  }
  const s = u.toString();
  return s ? "?" + s : "";
}

// ------------------------------------------------------------------ Stammdaten
export const stamm = { konten: [], tags: [], empfaenger: [], empfaengerFolge: [] };

export async function stammLaden() {
  const [konten, tags, empfaenger] = await Promise.all([
    api("GET", "/api/konten"), api("GET", "/api/tags"), api("GET", "/api/empfaenger")]);
  stamm.konten = konten;
  stamm.tags = tags;
  stamm.empfaenger = empfaenger.slice().sort(nachName);
  stamm.empfaengerFolge = empfaenger;   // Reihenfolge der Antwort (oberflaeche.md 23.2)
  return stamm;
}

export const kontoNach = (id) => stamm.konten.find((k) => k.id === id);

export function kontoPfad(k) {
  if (!k) return "";
  const teile = [];
  const gesehen = new Set();
  let x = k;
  while (x && !gesehen.has(x.id)) {
    gesehen.add(x.id);
    teile.unshift(x.name);
    x = x.eltern_id ? kontoNach(x.eltern_id) : null;
  }
  return teile.join(" › ");
}

export const pfadVon = (id) => kontoPfad(kontoNach(id));

/** Konten als Baum in Tiefensuche (Geschwister nach Name, localeCompare deutsch), je mit Ebene ab 1. */
export function baumFolge(konten) {
  const ids = new Set(konten.map((k) => k.id));
  const kinder = new Map();
  for (const k of konten) {
    const e = k.eltern_id && ids.has(k.eltern_id) ? k.eltern_id : 0;
    if (!kinder.has(e)) kinder.set(e, []);
    kinder.get(e).push(k);
  }
  const aus = [];
  const besuche = (e, ebene) => {
    for (const k of (kinder.get(e) || []).sort(nachName)) {
      aus.push({ konto: k, ebene, kinder: (kinder.get(k.id) || []).length });
      besuche(k.id, ebene + 1);
    }
  };
  besuche(0, 1);
  return aus;
}

export const kategorien = () => baumFolge(stamm.konten.filter((k) => k.art === "aufwand" || k.art === "ertrag"));

/** Klasse eines Kontos (datenmodell.md 2): Bestand, Aufwand, Ertrag, Eigenkapital. */
export const klasse = (k) => (BESTAND.has(k.art) ? "bestand" : k.art);

// ------------------------------------------------------------------ Ebenen (Menü, Dialog, Palette, Menü mobil)
export const ebenen = [];

export function ebeneOeffnen(ebene) {
  ebenen.push(ebene);
  return ebene;
}

export function ebeneSchliessen(ebene) {
  const i = ebenen.indexOf(ebene);
  if (i >= 0) ebenen.splice(i, 1);
}

export const obersteEbene = () => ebenen[ebenen.length - 1] || null;
export const dialogOffen = () => ebenen.some((e) => e.art === "dialog");

// ------------------------------------------------------------------ Meldungen (4.3)
const MAX_MELDUNGEN = 3;

export function melde(art, text, extra) {
  const box = tid("meldungen");
  const attrs = { class: "meldung meldung-" + art, tid: "meldung", "data-art": art };
  if (art === "fehler") attrs.role = "alert";
  const el = h("div", attrs, h("span", { class: "meldung-text" }, text));
  if (extra && extra.link) {
    el.append(" ", h("a", { href: extra.link.href, tid: extra.link.tid }, extra.link.text));
  }
  if (extra && extra.rueckgaengig) {
    el.append(h("button", { type: "button", class: "meldung-knopf", tid: "meldung-rueckgaengig",
      onclick: () => { el.remove(); rueckgaengig(); } }, "Rückgängig"));
  }
  el.append(h("button", { type: "button", class: "meldung-knopf", tid: "meldung-schliessen",
    "aria-label": "Meldung schließen", onclick: () => el.remove() }, "×"));
  box.append(el);
  while (box.querySelectorAll('[data-testid="meldung"]').length > MAX_MELDUNGEN) box.firstElementChild.remove();
  const dauer = art === "fehler" ? 10000 : (extra && (extra.link || extra.rueckgaengig)) ? 12000 : 6000;
  setTimeout(() => el.remove(), dauer);
  return el;
}

export function fehlerMelden(e) {
  if (e && e.offline) return;           // der Offline-Hinweis genügt (18)
  if (e && e.status === 401) return;    // Weiterleitung zur Anmeldung läuft
  melde("fehler", e && e.message ? e.message : String(e));
}

// ------------------------------------------------------------------ Seitenbezug (vom Router gesetzt)
export const oberflaeche = {
  neuLaden: async () => {},       // aktuelle Seite mit dem Stand des Servers neu zeigen
  benachrichtigungen: async () => {},
  gehe: (pfad) => { location.assign(pfad); },
  istMobil: () => false,
};

// ------------------------------------------------------------------ Rückgängig/Wiederholen (11)
const rueckStapel = [];
const vorStapel = [];

export function stapelAnzeigen() {
  const r = tid("rueckgaengig-knopf");
  const w = tid("wiederholen-knopf");
  if (r) r.disabled = rueckStapel.length === 0;
  if (w) w.disabled = vorStapel.length === 0;
}

export async function hoechsteAenderung() {
  const s = await api("GET", "/api/aenderungen?pro_seite=1");
  return s.eintraege.length ? s.eintraege[0].id : 0;
}

async function aenderungenSeit(m) {
  const ids = [];
  for (let seite = 1; seite < 100; seite++) {
    const s = await api("GET", `/api/aenderungen?pro_seite=100&seite=${seite}`);
    let fertig = s.eintraege.length === 0;
    for (const a of s.eintraege) {
      if (a.id <= m) { fertig = true; break; }
      if (!(a.gruppe || "").startsWith("sync:")) ids.push(a.id);
    }
    if (fertig || seite * 100 >= s.gesamt) break;
  }
  return ids.sort((a, b) => a - b);
}

/**
 * Eigene Operation mit Wirkung auf den Buchbestand: höchste Änderungs-ID vorher merken, ausführen, die neuen
 * Änderungen (ohne Gruppe „sync:“) als einen Eintrag auf den Rückgängig-Stapel legen, Stand neu zeigen.
 * Gibt das Ergebnis von `ausfuehren` zurück oder wirft den Fehler (nach der Fehlermeldung) weiter.
 */
export async function aktion(ausfuehren, optionen) {
  let gestapelt;
  const reif = new Promise((r) => { gestapelt = r; });   // erledigt, sobald der Stapel feststeht (D-122)
  laufendeAktionen.add(reif);
  try {
    return await aktionAusfuehren(ausfuehren, optionen || {}, () => { gestapelt(); laufendeAktionen.delete(reif); });
  } finally {
    gestapelt();
    laufendeAktionen.delete(reif);
  }
}

const laufendeAktionen = new Set();

async function aktionAusfuehren(ausfuehren, o, stapelFertig) {
  let m;
  try { m = await hoechsteAenderung(); } catch (e) { fehlerMelden(e); throw e; }
  let ergebnis;
  let fehler = null;
  try { ergebnis = await ausfuehren(); } catch (e) { fehler = e; }
  if (!fehler && o.danach) o.danach(ergebnis);       // z. B. Dialog schließen, bevor neu geladen wird
  try {
    const neu = await aenderungenSeit(m);
    if (neu.length) {
      rueckStapel.push(neu);
      vorStapel.length = 0;
    }
  } catch (e) { /* Stapel bleibt unverändert */ }
  stapelAnzeigen();
  stapelFertig();
  if (fehler) {
    if (!o.stillBeiFehler) fehlerMelden(fehler);
  } else if (o.erfolg) {
    melde("erfolg", typeof o.erfolg === "function" ? o.erfolg(ergebnis) : o.erfolg, { rueckgaengig: true });
  }
  if (!o.ohneNeuLaden) await neuLadenSicher();
  if (fehler) throw fehler;
  return ergebnis;
}

async function neuLadenSicher() {
  try { await oberflaeche.neuLaden(); } catch (e) { fehlerMelden(e); }
  try { await oberflaeche.benachrichtigungen(); } catch (e) { /* Zähler bleibt */ }
}

// Rückgängig/Wiederholen laufen nacheinander: ein Tastendruck während einer laufenden Anfrage wird eingereiht,
// nicht verworfen (D-122). Das Neuladen danach gehört nicht zur Kette.
let stapelKette = Promise.resolve();

function nacheinander(schritt) {
  const p = stapelKette.then(schritt);
  stapelKette = p.catch(() => {});
  return p;
}

async function stapelSchritt(von, nach, text) {
  if (laufendeAktionen.size) await Promise.all([...laufendeAktionen]);   // eben ausgelöste Änderung zuerst stapeln
  if (!von.length) {
    melde("hinweis", von === rueckStapel ? "Es gibt nichts rückgängig zu machen." : "Es gibt nichts zu wiederholen.");
    return false;
  }
  const e = von.pop();
  try {
    const u = e.length === 1 ? await api("POST", `/api/aenderungen/${e[0]}/rueckgaengig`)
      : await api("POST", "/api/aenderungen/rueckgaengig", { aenderung_ids: e });
    nach.push([u.id]);
    melde("erfolg", text + u.beschreibung);
  } catch (f) {
    fehlerMelden(f);                    // 409 rueckgaengig_konflikt / bereits_rueckgaengig: Eintrag verworfen
  } finally {
    stapelAnzeigen();
  }
  return true;
}

export async function rueckgaengig() {
  if (await nacheinander(() => stapelSchritt(rueckStapel, vorStapel, "Rückgängig: "))) await neuLadenSicher();
}

export async function wiederholen() {
  if (await nacheinander(() => stapelSchritt(vorStapel, rueckStapel, "Wiederholt: "))) await neuLadenSicher();
}
