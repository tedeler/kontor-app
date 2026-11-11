/* Kontor – Tabs der Ansichten (Feature „tabs-gegenbuchung“, D-115 in ENTSCHEIDUNGEN.md).
 *
 * Jede Ansicht (Pfad ohne Abfrageteil) ist ein Tab. Ein offener Tab behält sein DOM und sein Seitenobjekt, solange
 * die Seite im Browser geöffnet ist; inaktive Tabs hängen nicht im Dokument (keine doppelten data-testid). Die
 * Liste der Tabs (Pfad, Abfrageteil, Titel) und der aktive Tab liegen im localStorage unter `kontor.tabs`.
 * Dieses Modul kennt nur den Zustand und die Leiste; das Zeigen der Seiten übernimmt der Router in haupt.js. */
import { h } from "./kern.js";

const SCHLUESSEL = "kontor.tabs";
const HOECHSTENS = 40;          // gespeicherte Tabs; ältere inaktive fallen beim Speichern weg
const SCROLLER = ".listen-spalte, .panel-inhalt";

export class Tabs {
  /** beiWahl(tab): Tab soll aktiv werden; beiSchliessen(tab, naechster): aktiver Tab wurde geschlossen. */
  constructor(leiste, haupt, { beiWahl, beiSchliessen }) {
    this.leiste = leiste;
    this.haupt = haupt;
    this.beiWahl = beiWahl;
    this.beiSchliessen = beiSchliessen;
    this.liste = [];
    this.aktiv = null;
    this.laden();
    this.zeichnen();
  }

  // ---------------------------------------------------------------- Speicherung
  laden() {
    try {
      const d = JSON.parse(localStorage.getItem(SCHLUESSEL));
      if (!d || d.version !== 1 || !Array.isArray(d.tabs)) return;
      for (const t of d.tabs.slice(0, HOECHSTENS)) {
        if (!t || typeof t.pfad !== "string" || !t.pfad.startsWith("/") || this.finden(t.pfad)) continue;
        const suche = typeof t.suche === "string" && (t.suche === "" || t.suche.startsWith("?")) ? t.suche : "";
        this.liste.push(this.neu(t.pfad, suche, typeof t.titel === "string" ? t.titel : ""));
      }
    } catch (e) { /* ungültig: ohne gespeicherte Tabs beginnen */ }
  }

  speichern() {
    try {
      const tabs = this.liste.slice(-HOECHSTENS).map((t) => ({ pfad: t.pfad, suche: t.suche, titel: t.titel }));
      localStorage.setItem(SCHLUESSEL, JSON.stringify({ version: 1, tabs, aktiv: this.aktiv ? this.aktiv.pfad : null }));
    } catch (e) { /* Speicher voll oder gesperrt: Tabs gelten nur in diesem Fenster */ }
  }

  // ---------------------------------------------------------------- Zustand
  neu(pfad, suche, titel) {
    return { pfad, suche, titel, name: null, el: null, seite: null, geladen: false, veraltet: false, scroll: null };
  }

  finden(pfad) { return this.liste.find((t) => t.pfad === pfad) || null; }

  /** Tab zum Pfad holen oder rechts neben dem aktiven anlegen. */
  holen(pfad, suche) {
    let t = this.finden(pfad);
    if (!t) {
      t = this.neu(pfad, suche, "");
      const i = this.aktiv ? this.liste.indexOf(this.aktiv) : -1;
      this.liste.splice(i < 0 ? this.liste.length : i + 1, 0, t);
    }
    return t;
  }

  /** Den bisher aktiven Tab verlassen: Scrollstände sichern, solange sein DOM noch angehängt ist. */
  verlassen() {
    const t = this.aktiv;
    if (!t || !t.el || !t.el.isConnected) return;
    t.scroll = { haupt: this.haupt.scrollTop, innen: [...t.el.querySelectorAll(SCROLLER)].map((el) => [el, el.scrollTop, el.scrollLeft]) };
    if (location.pathname === t.pfad) t.suche = location.search;
  }

  /** Den Scrollstand nach dem Wiederanhängen herstellen. */
  scrollHerstellen(t) {
    if (!t.scroll) { this.haupt.scrollTop = 0; return; }
    this.haupt.scrollTop = t.scroll.haupt;
    for (const [el, oben, links] of t.scroll.innen) if (el.isConnected) { el.scrollTop = oben; el.scrollLeft = links; }
  }

  aktivieren(t) {
    this.aktiv = t;
    this.zeichnen();
    this.speichern();
  }

  /** Abfrageteil des aktiven Tabs nachführen (Filter der Kontoansicht über history.replaceState). */
  urlGeaendert() {
    const t = this.aktiv;
    if (t && location.pathname === t.pfad && t.suche !== location.search) { t.suche = location.search; this.zeichnen(); this.speichern(); }
  }

  titelSetzen(t, titel) {
    if (t.titel === titel) return;
    t.titel = titel;
    this.zeichnen();
    this.speichern();
  }

  /** Nach einer Änderung am Buchbestand: alle anderen Tabs beim nächsten Zeigen neu laden. */
  andereVeraltet(ausser) {
    for (const t of this.liste) if (t !== ausser && t.geladen) t.veraltet = true;
  }

  /** Offline (oberflaeche.md 18): keine veralteten Daten in inaktiven Tabs behalten. */
  alleVerwerfen() {
    for (const t of this.liste) { t.el = null; t.seite = null; t.geladen = false; t.veraltet = false; t.scroll = null; }
  }

  schliessen(t) {
    const i = this.liste.indexOf(t);
    if (i < 0) return;
    this.liste.splice(i, 1);
    if (t === this.aktiv) {
      const naechster = this.liste[i] || this.liste[i - 1] || null;
      this.aktiv = null;
      this.zeichnen();
      this.speichern();
      this.beiSchliessen(t, naechster);
      return;
    }
    this.zeichnen();
    this.speichern();
    const z = this.leiste.querySelector("[aria-selected='true'] a");
    if (z) z.focus();
  }

  // ---------------------------------------------------------------- Leiste
  zeichnen() {
    const fokusPfad = this.leiste.contains(document.activeElement)
      ? (document.activeElement.closest("[data-pfad]") || {}).dataset?.pfad : null;
    this.leiste.replaceChildren(...this.liste.map((t) => this.reiter(t)));
    this.leiste.hidden = this.liste.length === 0;
    if (fokusPfad) {
      const el = this.leiste.querySelector(`[data-pfad="${CSS.escape(fokusPfad)}"] a`);
      if (el) el.focus();
    }
    const aktiv = this.leiste.querySelector("[aria-selected='true']");
    if (aktiv && aktiv.scrollIntoView) aktiv.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  reiter(t) {
    const aktiv = t === this.aktiv;
    const titel = t.titel || t.pfad;
    const link = h("a", { href: t.pfad + t.suche, class: "tab-titel", tid: "tab-titel", title: titel,
      tabindex: aktiv ? "0" : "-1" }, titel);
    link.addEventListener("click", (e) => {
      if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      if (t !== this.aktiv) this.beiWahl(t);
    });
    const zu = h("button", { type: "button", class: "tab-schliessen", tid: "tab-schliessen", tabindex: "-1",
      "aria-label": `Tab „${titel}“ schließen`, title: "Tab schließen" }, "×");
    zu.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); this.schliessen(t); });
    const el = h("div", { role: "tab", class: "tab" + (aktiv ? " tab-aktiv" : ""), tid: "tab", "data-pfad": t.pfad,
      "aria-selected": aktiv ? "true" : "false" }, link, zu);
    // Mittelklick schließt den Tab
    el.addEventListener("auxclick", (e) => { if (e.button === 1) { e.preventDefault(); this.schliessen(t); } });
    el.addEventListener("mousedown", (e) => { if (e.button === 1) e.preventDefault(); });
    el.addEventListener("keydown", (e) => this.taste(t, e));
    return el;
  }

  /** Tastatur in der Leiste: Pfeile wechseln den Fokus, Entf schließt, Enter/Leertaste aktivieren. */
  taste(t, e) {
    const i = this.liste.indexOf(t);
    const fokus = (j) => {
      const el = this.leiste.querySelectorAll(".tab-titel")[j];
      if (el) el.focus();
    };
    if (e.key === "ArrowRight") { e.preventDefault(); fokus((i + 1) % this.liste.length); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); fokus((i - 1 + this.liste.length) % this.liste.length); }
    else if (e.key === "Home") { e.preventDefault(); fokus(0); }
    else if (e.key === "End") { e.preventDefault(); fokus(this.liste.length - 1); }
    else if (e.key === "Delete") { e.preventDefault(); this.schliessen(t); }
    else if (e.key === " ") { e.preventDefault(); if (t !== this.aktiv) this.beiWahl(t); }
  }
}
