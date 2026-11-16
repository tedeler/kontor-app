/* Kontor – Ausdrucksfelder für Regeln und Kontoblatt-Filter (D-175): Hervorhebung, Prüfung über
   POST /api/ausdruck/pruefen, Fehlerstelle, einfache Vervollständigung, Treffer-Markierungen. */
import { api, h, neueId } from "./kern.js";

const SPRACHE = new Map();

/** Felder, Schlüsselwörter, Datumswörter je Kontext (GET /api/ausdruck/sprache), zwischengespeichert. */
export async function sprache(kontext) {
  if (!SPRACHE.has(kontext)) {
    SPRACHE.set(kontext, api("GET", `/api/ausdruck/sprache?kontext=${kontext}`).catch(() => {
      SPRACHE.delete(kontext);
      return { felder: [], schluesselwoerter: [], methoden: [] };
    }));
  }
  return SPRACHE.get(kontext);
}

// --------------------------------------------------------------- Hervorhebung
const LEX = /(\s+)|(#[^\n]*)|([rR]?"(?:[^"\\\n]|\\.)*"?|[rR]?'(?:[^'\\\n]|\\.)*'?)|(\d{4}-\d{2}-\d{2}|\d{4}-[qQ][1-4]|\d{4}-\d{2}|\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})?|\d{1,2}\/\d{4}|[+-]?\d+[dDtTwWmMqQyYjJ](?![\wäöüß]))|(\d[\d_]*(?:\.\d+)?)|([A-Za-zÄÖÜäöüß_][\wÄÖÜäöüß]*)|(==|!=|<=|>=|&&|\|\||\.\.|[<>!()[\],.+\-/=])|(.)/gy;
const SCHLUESSEL = new Set(["and", "or", "not", "in", "is", "none", "null", "true", "false"]);
const DATUMSWORT = /^(heute|gestern|vorgestern|morgen|diese_woche|letzte_woche|naechste_woche|nächste_woche|dieser_monat|letzter_monat|naechster_monat|nächster_monat|dieses_quartal|letztes_quartal|naechstes_quartal|dieses_jahr|letztes_jahr|vorjahr|naechstes_jahr|jan|januar|feb|februar|mär|maer|mrz|märz|apr|april|mai|jun|juni|jul|juli|aug|august|sep|sept|september|okt|oktober|nov|november|dez|dezember|q[1-4]|kw\d{1,2})$/i;

/** Zerlegt den Text in Abschnitte {art, text}; `felder` = Set gültiger Feldnamen (auch Kurzformen). */
export function zerlegen(text, felder) {
  const aus = [];
  LEX.lastIndex = 0;
  let m;
  while (LEX.lastIndex < text.length && (m = LEX.exec(text))) {
    const [t, ws, kom, str, datum, zahl, ident, op] = m;
    let art = "sonst";
    if (ws) art = "leer";
    else if (kom) art = "kommentar";
    else if (str) art = /^[rR]/.test(str) ? "regex" : "text";
    else if (datum) art = "datum";
    else if (zahl) art = "zahl";
    else if (ident) {
      const k = ident.toLowerCase();
      if (SCHLUESSEL.has(k)) art = "schluessel";
      else if (felder && felder.has(k.replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue"))) art = "feld";
      else if (DATUMSWORT.test(ident)) art = "datum";
      else if (["startswith", "endswith", "search", "case", "fold"].includes(k)) art = "methode";
      else art = "wort";
    } else if (op) art = op === "&&" || op === "||" || op === "!" ? "schluessel" : "op";
    aus.push({ art, text: t });
  }
  return aus;
}

/** Span bzw. Textknoten mit unverändertem Text (h() lässt reine Leerzeichen weg). */
const span = (cls, text) => { const s = h("span", cls ? { class: cls } : null); s.textContent = text; return s; };
const textKnoten = (text) => document.createTextNode(text);

const falten = (s) => s.toLowerCase().replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue");

/** Ausdruck als hervorgehobene Elemente (z. B. in der Regelliste). */
export function hervorgehoben(text, felder) {
  return h("code", { class: "ausdruck-code" }, zerlegen(text, felder).map((t) =>
    span(`az-${t.art}`, t.text)));
}

/** Feldnamen (gefaltet) aus der Sprachbeschreibung. */
export function feldMenge(sp) {
  const s = new Set();
  for (const f of sp.felder || []) {
    s.add(falten(f.name));
    if (f.kurz) s.add(falten(f.kurz));
  }
  return s;
}

/** Text eines Felds mit <mark> an den Treffer-Markierungen ({feld, start, ende}) der Liste bzw. des Tests. */
export function markiert(text, markierungen, feld) {
  const m = (markierungen || []).filter((x) => x.feld === feld).sort((a, b) => a.start - b.start);
  if (!m.length || !text) return text || "";
  const teile = [];
  let pos = 0;
  for (const x of m) {
    if (x.start < pos) continue;
    if (x.start > pos) teile.push(textKnoten(text.slice(pos, x.start)));
    const m = h("mark", { class: "treffer" });
    m.textContent = text.slice(x.start, x.ende);
    teile.push(m);
    pos = x.ende;
  }
  if (pos < text.length) teile.push(textKnoten(text.slice(pos)));
  return teile;
}

// ------------------------------------------------------------------ Eingabe
/**
 * Eingabefeld für Ausdrücke. Optionen: kontext ("regel" | "filter"), wert, tid, beschriftung, zeilen (1 = einzeilig,
 * Enter löst `beiEnter` aus), platzhalter, beiErgebnis(ergebnis) nach jeder Prüfung, beiEnter(ergebnis).
 * Eigenschaften: el (Hülle), eingabe (textarea), ergebnis (letzte Antwort von /pruefen), wert, pruefen().
 */
export class AusdruckEingabe {
  constructor(o) {
    this.o = o;
    this.kontext = o.kontext || "filter";
    this.felder = new Set();
    this.ergebnis = null;
    this.nr = 0;
    const id = neueId("ausdruck");
    const fehlerId = `${id}-fehler`;
    this.eingabe = h("textarea", { id, class: "ausdruck-text", rows: String(o.zeilen || 1), spellcheck: "false",
      autocomplete: "off", autocapitalize: "off", tid: o.tid, "aria-describedby": fehlerId,
      "aria-autocomplete": "list", placeholder: o.platzhalter || "", "aria-label": o.beschriftung || "Ausdruck" });
    this.eingabe.value = o.wert || "";
    this.schicht = h("pre", { class: "ausdruck-schicht", "aria-hidden": "true" });
    this.status = h("span", { class: "ausdruck-status", tid: o.tid ? `${o.tid}-status` : null, "data-status": "leer",
      "aria-hidden": "true" });
    this.fehlerEl = h("p", { id: fehlerId, class: "ausdruck-fehler", tid: o.tid ? `${o.tid}-fehler` : null,
      role: "status", "aria-live": "polite" });
    this.liste = h("ul", { class: "ausdruck-vorschlaege", role: "listbox", hidden: true, id: `${id}-liste` });
    this.eingabe.setAttribute("aria-controls", `${id}-liste`);
    this.el = h("div", { class: "ausdruck-eingabe" + ((o.zeilen || 1) > 1 ? " mehrzeilig" : "") },
      h("div", { class: "ausdruck-feld" }, this.schicht, this.eingabe, this.status), this.liste, this.fehlerEl);
    this.ereignisse();
    sprache(this.kontext).then((sp) => {
      this.sp = sp;
      this.felder = feldMenge(sp);
      this.zeichnen();
    });
    this.zeichnen();
    if (this.eingabe.value.trim()) this.pruefen();
  }

  get wert() { return this.eingabe.value; }

  set wert(t) {
    this.eingabe.value = t;
    this.zeichnen();
    this.pruefen();
  }

  ereignisse() {
    const e = this.eingabe;
    e.addEventListener("input", () => {
      this.zeichnen();
      this.vorschlagen();
      clearTimeout(this.uhr);
      this.uhr = setTimeout(() => this.pruefen(), 300);
    });
    e.addEventListener("scroll", () => { this.schicht.scrollTop = e.scrollTop; this.schicht.scrollLeft = e.scrollLeft; });
    e.addEventListener("keydown", (ev) => this.taste(ev));
    e.addEventListener("blur", () => setTimeout(() => { this.liste.hidden = true; }, 150));
    this.fehlerEl.addEventListener("click", () => {
      const f = this.ergebnis && this.ergebnis.fehler && this.ergebnis.fehler[0];
      if (f) this.cursorAuf(f.zeile, f.spalte);
    });
  }

  cursorAuf(zeile, spalte) {
    const z = this.eingabe.value.split("\n");
    let off = 0;
    for (let i = 0; i < zeile - 1 && i < z.length; i++) off += z[i].length + 1;
    off += spalte - 1;
    this.eingabe.focus();
    this.eingabe.setSelectionRange(off, off);
  }

  /** Overlay mit Hervorhebung; die Fehlerstelle ist unterwellt. */
  zeichnen() {
    const text = this.eingabe.value;
    const f = this.ergebnis && !this.ergebnis.gueltig && this.ergebnis.fehler && this.ergebnis.fehler[0];
    let von = -1;
    let bis = -1;
    if (f && this.ergebnisText === text) {
      const z = text.split("\n");
      const off = (zeile, spalte) => z.slice(0, zeile - 1).reduce((s, x) => s + x.length + 1, 0) + spalte - 1;
      von = off(f.zeile, f.spalte);
      bis = Math.max(von + 1, off(f.ende_zeile, f.ende_spalte));
    }
    const kinder = [];
    let pos = 0;
    for (const t of zerlegen(text, this.felder)) {
      const a = pos;
      const b = pos + t.text.length;
      pos = b;
      const cls = `az-${t.art}` + (von >= 0 && a < bis && b > von ? " az-fehler" : "");
      kinder.push(span(cls, t.text));
    }
    kinder.push(span(null, "\u200b"));   // letzte Zeile mit Zeilenumbruch sichtbar halten
    this.schicht.replaceChildren(...kinder);
    this.eingabe.dataset.leer = text.trim() ? "nein" : "ja";
  }

  async pruefen() {
    const text = this.eingabe.value;
    const nr = ++this.nr;
    if (!text.trim()) {
      this.ergebnis = null;
      this.ergebnisText = text;
      this.status.dataset.status = "leer";
      this.eingabe.removeAttribute("aria-invalid");
      this.fehlerEl.textContent = "";
      this.zeichnen();
      if (this.o.beiErgebnis) this.o.beiErgebnis(null);
      return null;
    }
    this.status.dataset.status = "pruefe";
    let r;
    try {
      r = await api("POST", "/api/ausdruck/pruefen", { ausdruck: text, kontext: this.kontext });
    } catch (e) {
      if (nr === this.nr) this.status.dataset.status = "leer";
      return null;
    }
    if (nr !== this.nr) return this.ergebnis;
    this.ergebnis = r;
    this.ergebnisText = text;
    this.status.dataset.status = r.gueltig ? "ok" : "fehler";
    this.status.textContent = r.gueltig ? "✓" : "✗";
    if (r.gueltig) {
      this.eingabe.removeAttribute("aria-invalid");
      const hinweis = (r.hinweise || [])[0];
      this.fehlerEl.textContent = hinweis ? hinweis.meldung : "";
      this.fehlerEl.dataset.art = hinweis ? "hinweis" : "";
    } else {
      this.eingabe.setAttribute("aria-invalid", "true");
      const f = r.fehler[0];
      const ort = this.eingabe.value.includes("\n") ? `Zeile ${f.zeile}, Spalte ${f.spalte}: ` : `Spalte ${f.spalte}: `;
      this.fehlerEl.textContent = ort + f.meldung;
      this.fehlerEl.dataset.art = "fehler";
      this.fehlerEl.dataset.code = f.code;
    }
    this.zeichnen();
    if (this.o.beiErgebnis) this.o.beiErgebnis(r);
    return r;
  }

  async taste(ev) {
    if (!this.liste.hidden) {
      const opts = [...this.liste.children];
      let i = opts.findIndex((x) => x.getAttribute("aria-selected") === "true");
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        i = (i + (ev.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length;
        opts.forEach((x, j) => x.setAttribute("aria-selected", String(j === i)));
        this.eingabe.setAttribute("aria-activedescendant", opts[i].id);
        return;
      }
      if ((ev.key === "Enter" || ev.key === "Tab") && i >= 0) {
        ev.preventDefault();
        this.uebernehmen(opts[i].dataset.wert);
        return;
      }
      if (ev.key === "Escape") {
        ev.preventDefault();
        ev.stopPropagation();
        this.liste.hidden = true;
        return;
      }
    }
    if (ev.key === "Enter" && (this.o.zeilen || 1) === 1) {
      ev.preventDefault();
      clearTimeout(this.uhr);
      const r = await this.pruefen();
      if (this.o.beiEnter) this.o.beiEnter(r);
    }
  }

  /** Vervollständigung für das Wort vor dem Cursor: Felder, Schlüsselwörter, Methoden, Datumswörter. */
  vorschlagen() {
    const e = this.eingabe;
    const vor = e.value.slice(0, e.selectionStart);
    if (/["'][^"']*$/.test(vor.replace(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, ""))) { this.liste.hidden = true; return; }
    const m = /([A-Za-zÄÖÜäöüß_][\wÄÖÜäöüß]*)$/.exec(vor);
    if (!m || !this.sp || m[1].length < 1) { this.liste.hidden = true; return; }
    const wort = falten(m[1]);
    const nachPunkt = vor.slice(0, vor.length - m[1].length).endsWith(".");
    const kandidaten = [];
    if (nachPunkt) for (const x of this.sp.methoden || []) kandidaten.push([x, "Methode"]);
    else {
      for (const f of this.sp.felder || []) {
        kandidaten.push([f.name, f.bezeichnung]);
        if (f.kurz) kandidaten.push([f.kurz, `${f.bezeichnung} (Kurzform)`]);
      }
      for (const k of ["and", "or", "not", "in", "is", "None", "True", "False"]) kandidaten.push([k, "Schlüsselwort"]);
      if (this.sp.datum) for (const w of [...this.sp.datum.tagwoerter, ...this.sp.datum.zeitwoerter]) kandidaten.push([w, "Datum"]);
    }
    const passend = kandidaten.filter(([k]) => falten(k).startsWith(wort) && falten(k) !== wort).slice(0, 8);
    if (!passend.length) { this.liste.hidden = true; return; }
    this.ersetzeAb = e.selectionStart - m[1].length;
    this.liste.replaceChildren(...passend.map(([k, t], i) => h("li", { role: "option", id: `${e.id}-v${i}`,
      "aria-selected": String(i === 0), "data-wert": k,
      onmousedown: (ev) => { ev.preventDefault(); this.uebernehmen(k); } }, h("span", { class: "az-feld" }, k), " ",
    h("span", { class: "klein" }, t))));
    this.liste.hidden = false;
    e.setAttribute("aria-activedescendant", `${e.id}-v0`);
  }

  uebernehmen(wert) {
    const e = this.eingabe;
    const ende = e.selectionStart;
    e.value = e.value.slice(0, this.ersetzeAb) + wert + e.value.slice(ende);
    const pos = this.ersetzeAb + wert.length;
    e.setSelectionRange(pos, pos);
    this.liste.hidden = true;
    e.removeAttribute("aria-activedescendant");
    e.dispatchEvent(new Event("input"));
  }
}

/** Erkennt die alte Zeilenform der Regelbedingungen („empfaenger enthaelt REWE“) für die Kompatibilität. */
export function alteBedingungen(text) {
  const zeilen = text.split("\n").map((z) => z.trim()).filter(Boolean);
  if (!zeilen.length) return null;
  const re = /^(empfaenger|verwendungszweck|betrag|konto_id)\s+(enthaelt|gleich|beginnt_mit|mindestens|hoechstens)\s+(.+)$/;
  return zeilen.every((z) => re.test(z)) ? zeilen.map((z) => re.exec(z).slice(1)) : null;
}
