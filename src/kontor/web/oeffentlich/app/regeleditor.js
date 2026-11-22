/* Kontor – Regelliste, Regeleditor (Baukasten und Ausdruck) und Testbereich (D-185, Konzept 5.1–5.3). */
import {
  BESTAND, aktion, api, baumFolge, betragEl, betragLesen, datumText, fehlerText, h, kategorien, kontoPfad, melde, neueId, pfadVon,
  stamm,
} from "./kern.js";
import { bestaetigen, dialog, feld, imDialog, knopf, knopfLeiste } from "./ui.js";
import { AusdruckEingabe, alteBedingungen, feldMenge, hervorgehoben, markiert, sprache } from "./ausdruck.js";

/** Text in die Zwischenablage; ohne sicheren Kontext (http im Heimnetz) über ein verstecktes Textfeld. */
export async function kopieren(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
  } catch (e) { /* Rückfall unten */ }
  const ta = h("textarea", { "aria-hidden": "true", readonly: true, stil: { position: "fixed", left: "-9999px", top: "0" } });
  ta.value = text;
  document.body.append(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  ta.remove();
  return ok;
}

/** Beschriftetes Ausdrucksfeld (das Label zeigt auf das Textfeld). */
export function ausdruckFeld(beschriftung, ae, hinweis) {
  return h("div", { class: "feld" }, h("label", { for: ae.eingabe.id }, beschriftung), ae.el,
    hinweis ? h("small", { class: "hinweis" }, hinweis) : null);
}

const MODUS_SCHLUESSEL = "kontor.regel.modus";
const modusLesen = () => { try { return localStorage.getItem(MODUS_SCHLUESSEL) || "ausdruck"; } catch { return "ausdruck"; } };
const modusSchreiben = (m) => { try { localStorage.setItem(MODUS_SCHLUESSEL, m); } catch { /* ohne Speicher */ } };

export const WIRKUNG_TEXT = { neu: "neu", abweichend: "abweichend", bereits_so: "bereits so", verdeckt: "verdeckt",
  uebersprungen: "übersprungen", treffer: "Treffer" };

// ------------------------------------------------------------------ Regelliste (5.1)
const anzahlText = (n, eins, viele) => `${n} ${n === 1 ? eins : viele}`;

export async function regelnSeite(seite, kopf) {
  const [liste, sp] = await Promise.all([api("GET", "/api/regeln"), sprache("regel")]);
  const felder = feldMenge(sp);
  kopf(seite, "Regeln",
    knopf("Regel anlegen", { tid: "regel-anlegen", class: "knopf knopf-haupt", onclick: (e) => regelEditor(null, e.currentTarget) }),
    // aus main (D-178/D-179): Zähler beim Anwenden, Vorschläge des Lernmodells, Link zum Lernmodell
    knopf("Regeln anwenden", { tid: "regeln-anwenden",
      title: "Alle aktiven Regeln auf vorhandene Buchungen anwenden. Treffer werden als Vorschlag gesetzt.",
      onclick: async () => {
        try {
          await aktion(() => api("POST", "/api/regeln/anwenden", {}), { erfolg: (r) =>
            `Regeln angewendet: ${r.anzahl} von ${anzahlText(r.geprueft, "geprüften Buchung", "geprüften Buchungen")} `
            + `${r.anzahl === 1 ? "hat" : "haben"} einen Vorschlag erhalten.` });
        } catch (e) { /* gemeldet */ }
      } }),
    knopf("Vorschläge für unkategorisierte Buchungen", { tid: "lernmodell-anwenden",
      title: "Fragt das Lernmodell für alle Buchungen, die noch auf „Unkategorisiert“ stehen. Ab "
        + "70 % Sicherheit wird die Kategorie als Vorschlag gesetzt; du nimmst ihn an oder lehnst ihn ab. "
        + "Kategorisierte Buchungen bleiben unverändert. Das Modell lernt ohnehin laufend aus deinen Zuordnungen.",
      onclick: async () => {
        try {
          await aktion(() => api("POST", "/api/lernmodell/anwenden", {}), { erfolg: (r) => {
            if (!r.geprueft) return "Es gibt keine unkategorisierten Buchungen.";
            const offen = r.geprueft - r.anzahl;
            return `${r.anzahl} von ${anzahlText(r.geprueft, "unkategorisierten Buchung", "unkategorisierten Buchungen")} `
              + `${r.anzahl === 1 ? "hat" : "haben"} einen Vorschlag erhalten`
              + (offen ? `; ${offen} ${offen === 1 ? "bleibt" : "bleiben"} offen (Grund in den Einzelheiten der Buchung).` : ".");
          } });
        } catch (e) { /* gemeldet */ }
      } }),
    h("a", { href: "/lernmodell", class: "knopf", tid: "regeln-lernmodell" }, "Lernmodell …"));
  if (!liste.length) {
    seite.append(h("p", { class: "leer" }, "Noch keine Regeln. Regeln ordnen neuen Buchungen eine Kategorie zu, bevor das Lernmodell gefragt wird, und können Tags vergeben."));
    return { titel: "Regeln" };
  }
  const ul = h("ol", { class: "regel-liste", tid: "regel-liste", "aria-label": "Regeln in der Reihenfolge ihrer Anwendung" });
  const reihenfolgeSenden = async (ids) => {
    try { await aktion(() => api("POST", "/api/regeln/reihenfolge", { regel_ids: ids }), { erfolg: "Reihenfolge geändert." }); }
    catch (e) { /* gemeldet */ }
  };
  const ids = liste.map((r) => r.id);
  const verschieben = (id, um) => {
    const i = ids.indexOf(id);
    const j = i + um;
    if (j < 0 || j >= ids.length) return;
    const neu = ids.slice();
    [neu[i], neu[j]] = [neu[j], neu[i]];
    reihenfolgeSenden(neu);
  };
  let gezogen = null;
  liste.forEach((r, i) => {
    const aktiv = h("input", { type: "checkbox", tid: `regel-aktiv-${r.id}`, checked: r.aktiv,
      "aria-label": `Regel ${r.name} aktiv` });
    aktiv.addEventListener("change", async () => {
      try { await aktion(() => api("PATCH", `/api/regeln/${r.id}`, { aktiv: aktiv.checked }), { erfolg: aktiv.checked ? "Regel aktiviert." : "Regel deaktiviert." }); }
      catch (e) { aktiv.checked = !aktiv.checked; }
    });
    const griff = h("button", { type: "button", class: "regel-griff", tid: `regel-griff-${r.id}`,
      "aria-label": `Regel ${r.name} verschieben (Alt+Pfeil hoch/runter)`, title: "Ziehen oder Alt+↑/↓" }, "⠿");
    griff.addEventListener("keydown", (e) => {
      if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) { e.preventDefault(); verschieben(r.id, e.key === "ArrowUp" ? -1 : 1); }
    });
    const li = h("li", { tid: `regel-${r.id}`, class: "karte regel-zeile" + (r.aktiv ? "" : " inaktiv"), draggable: "true",
      "data-id": String(r.id) },
    griff, h("span", { class: "regel-nr" }, `${i + 1}.`), aktiv,
    h("div", { class: "regel-inhalt" },
      h("strong", null, r.name), h("span", { class: "regel-ziel", tid: `regel-ziel-${r.id}` },
        r.kategorie_id ? ` → ${pfadVon(r.kategorie_id)} ` : (r.tag_ids || []).length ? " → " : " → (keine Aktion) ",
        (r.tag_ids || []).map((id) => h("span", { class: "tag" }, `+ ${tagName(id)}`))),
      r.automatisch ? h("span", { class: "regel-auto", tid: `regel-automatisch-${r.id}`,
        title: "Aus deinen Zuordnungen gelernt. Wird die Regel gelöscht, legt Kontor sie für diesen Empfänger nicht wieder an." },
      "automatisch angelegt") : null,
      h("div", { class: "regel-bedingung", tid: `regel-ausdruck-${r.id}`, title: r.ausdruck }, hervorgehoben(r.ausdruck || "", felder))),
    knopfLeiste(
      knopf("Bearbeiten…", { "aria-label": `Bearbeiten: Regel ${r.name}`, onclick: (e) => regelEditor(r, e.currentTarget) }),
      knopf("Duplizieren", { "aria-label": `Regel ${r.name} duplizieren`, onclick: (e) =>
        regelEditor({ ...r, id: null, name: `${r.name} (Kopie)` }, e.currentTarget) }),
      knopf("Löschen", { "aria-label": `Regel ${r.name} löschen`, onclick: async (e) => {
        if (!(await bestaetigen(`Regel „${r.name}“ löschen?`, { ja: "Löschen", ausloeser: e.currentTarget }))) return;
        try { await aktion(() => api("DELETE", `/api/regeln/${r.id}`), { erfolg: "Regel gelöscht." }); } catch (f) { /* gemeldet */ }
      } })));
    li.addEventListener("dragstart", (e) => { gezogen = r.id; e.dataTransfer.effectAllowed = "move"; li.classList.add("zieht"); });
    li.addEventListener("dragend", () => { li.classList.remove("zieht"); gezogen = null; });
    li.addEventListener("dragover", (e) => { if (gezogen !== null && gezogen !== r.id) { e.preventDefault(); li.classList.add("ziel"); } });
    li.addEventListener("dragleave", () => li.classList.remove("ziel"));
    li.addEventListener("drop", (e) => {
      e.preventDefault();
      li.classList.remove("ziel");
      if (gezogen === null || gezogen === r.id) return;
      const neu = ids.filter((x) => x !== gezogen);
      neu.splice(neu.indexOf(r.id) + (ids.indexOf(gezogen) < ids.indexOf(r.id) ? 1 : 0), 0, gezogen);
      reihenfolgeSenden(neu);
    });
    ul.append(li);
  });
  seite.append(h("p", { class: "hinweis klein" }, "Regeln wirken von oben nach unten; für die Kategorie gilt die erste passende Regel, Tags vergeben alle passenden Regeln. "
    + "Reihenfolge per Ziehen oder Alt+↑/↓ am Griff."), ul);
  return { titel: "Regeln" };
}

// ------------------------------------------------------------------ Baukasten (5.2)
const OPS = {
  text: [["enthaelt", "enthält"], ["enthaelt_nicht", "enthält nicht"], ["ist", "ist"], ["ist_nicht", "ist nicht"],
    ["beginnt", "beginnt mit"], ["endet", "endet mit"], ["regex", "entspricht Regex"], ["regex_nicht", "entspricht Regex nicht"]],
  betrag: [[">", "größer als"], [">=", "mindestens"], ["<", "kleiner als"], ["<=", "höchstens"], ["==", "gleich"], ["!=", "ungleich"], ["zwischen", "zwischen"]],
  auswahl: [["==", "ist"], ["!=", "ist nicht"]],
  konto: [["==", "ist"], ["!=", "ist nicht"]],
  kategorie: [["==", "ist"], ["!=", "ist nicht"], ["leer", "ist leer"], ["nicht_leer", "ist nicht leer"]],
  tags: [["hat", "hat Tag"], ["hat_nicht", "hat Tag nicht"]],
  bool: [["wahr", "ja"], ["falsch", "nein"]],
};
OPS.int = OPS.betrag;
// nur im Filter (D-194): Datum mit Zeitangaben nach Konzept 4.6, Freitext wie die Volltextsuche
OPS.datum = [["in", "liegt in"], ["not in", "nicht in"], [">=", "ab"], ["<=", "bis"], [">", "nach"], ["<", "vor"]];
OPS.frei = [["enthaelt", "enthält"]];
export const FREITEXT = { name: "__frei", kurz: null, typ: "frei", bezeichnung: "Freitext (Empfänger, Zweck, Notiz, Tags)" };
const MONATE = ["", "jan", "feb", "mär", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "dez"];

const q = (s) => JSON.stringify(String(s));
const roh = (s) => (s.includes('"') || s.endsWith("\\") ? q(s) : `r"${s}"`);
const centText = (c) => (c % 100 === 0 ? String(Math.trunc(c / 100)) : `${Math.trunc(c / 100)}.${String(Math.abs(c % 100)).padStart(2, "0")}`);

function zeileText(z, sp) {
  const f = z.feld === FREITEXT.name ? FREITEXT : sp.felder.find((x) => x.name === z.feld);
  if (!f) return null;
  const n = f.name;
  const w = z.wert ?? "";
  const zahl = (x) => {
    if (f.typ !== "betrag") return String(x).trim();
    const c = betragLesen(String(x));
    return typeof c === "number" ? centText(Math.abs(c)) : null;
  };
  switch (f.typ) {
    case "frei": return String(w).trim() ? q(w) : null;
    case "datum": return String(w).trim() ? `${n} ${z.op} ${String(w).trim()}` : null;
    case "text":
      if (z.op === "enthaelt") return `${q(w)} in ${n}`;
      if (z.op === "enthaelt_nicht") return `${q(w)} not in ${n}`;
      if (z.op === "ist") return `${n} == ${q(w)}`;
      if (z.op === "ist_nicht") return `${n} != ${q(w)}`;
      if (z.op === "beginnt") return `${n}.startswith(${q(w)})`;
      if (z.op === "endet") return `${n}.endswith(${q(w)})`;
      if (z.op === "regex") return `${n}.search(${roh(w)})`;
      return `not ${n}.search(${roh(w)})`;
    case "betrag": case "int": {
      const a = zahl(w);
      if (a === null || a === "") return null;
      if (z.op === "zwischen") {
        const b = zahl(z.wert2 ?? "");
        return b === null || b === "" ? null : `${a} <= ${n} <= ${b}`;
      }
      return `${n} ${z.op} ${a}`;
    }
    case "auswahl": case "konto": return `${n} ${z.op} ${q(w)}`;
    case "kategorie":
      if (z.op === "leer") return `${n} is None`;
      if (z.op === "nicht_leer") return `${n} is not None`;
      return `${n} ${z.op} ${q(w)}`;
    case "tags": return z.op === "hat" ? `${q(w)} in ${n}` : `${q(w)} not in ${n}`;
    case "bool": return z.op === "wahr" ? n : `not ${n}`;
    default: return null;
  }
}

/** Baukasten-Modell {verkn, teile: [zeile | {verkn, teile}]} → Ausdruckstext (oder null, wenn unvollständig). */
export function baukastenText(m, sp, leereAuslassen = false) {
  const teil = (x) => {
    if (x.teile) {
      let t = x.teile.map((y) => zeileText(y, sp));
      if (leereAuslassen) t = t.filter((y) => y !== null);
      if (t.some((y) => y === null) || !t.length) return leereAuslassen ? "" : null;
      return t.length === 1 ? t[0] : `(${t.join(` ${x.verkn} `)})`;
    }
    return zeileText(x, sp);
  };
  let t = m.teile.map(teil);
  if (leereAuslassen) {   // im Filter: leere Zeilen zählen nicht (D-194)
    t = t.filter((x) => x);
    return t.join(` ${m.verkn} `);
  }
  if (!t.length || t.some((x) => x === null)) return null;
  return t.join(` ${m.verkn} `);
}

/** Zeitangabe des Baums als Text (wie ``ausdruck.zeit_text`` auf dem Server). */
export function zeitText(z) {
  const zw = (n) => String(n).padStart(2, "0");
  switch (z.a) {
    case "tag": return `${zw(z.d)}.${zw(z.m)}.${z.j ?? ""}`;
    case "jahr": return String(z.j);
    case "monat": return z.j != null ? `${z.m}/${z.j}` : MONATE[z.m];
    case "quartal": return `q${z.q}${z.j != null ? `/${z.j}` : ""}`;
    case "kw": return `kw${z.w}${z.j != null ? `/${z.j}` : ""}`;
    case "wort": return z.w;
    case "rel": return `${z.vz}${z.n}${z.e}`;
    case "plus": return `${zeitText(z.basis)} ${z.vz} ${z.n}${z.e}`;
    default: return `${zeitText(z.von)} .. ${zeitText(z.bis)}`;
  }
}

/** Typisierter Baum (POST /api/ausdruck/pruefen) → Baukasten-Modell, oder null, wenn nicht darstellbar. */
export function baukastenAusBaum(b, sp) {
  const typ = (name) => (name === FREITEXT.name ? "frei" : (sp.felder.find((f) => f.name === name) || {}).typ);
  const wertText = (x) => {
    if (x.t === "text" || x.t === "auswahl") return x.wert;
    if (x.t === "betrag") return centText(x.cent).replace(".", ",");
    if (x.t === "int") return String(x.wert);
    if (x.t === "zeit") return zeitText(x.z);
    if (x.t === "ref") return x.art === "tag" ? ((stamm.tags.find((t) => t.id === x.id) || {}).name || `#${x.id}`) : pfadVon(x.id);
    return null;
  };
  const NEG = { enthaelt: "enthaelt_nicht", ist: "ist_nicht", regex: "regex_nicht", "==": "!=", hat: "hat_nicht", leer: "nicht_leer", wahr: "falsch" };
  const blatt = (x) => {
    if (x.t === "nicht") {
      const y = blatt(x.x);
      return y && NEG[y.op] ? { ...y, op: NEG[y.op] } : null;
    }
    if (x.t === "feld" && typ(x.name) === "bool") return { feld: x.name, op: "wahr" };
    if (x.t === "freitext") return { feld: FREITEXT.name, op: "enthaelt", wert: x.wert };
    if (x.t === "methode") return { feld: x.feld, op: { startswith: "beginnt", endswith: "endet", search: "regex" }[x.name], wert: x.muster,
      _ok: !x.case && x.fold };
    if (x.t !== "kette") return null;
    const [a, c] = x.terme;
    if (x.terme.length === 3) {
      if (x.ops[0] !== "<=" || x.ops[1] !== "<=" || x.terme[1].t !== "feld") return null;
      return { feld: x.terme[1].name, op: "zwischen", wert: wertText(a), wert2: wertText(x.terme[2]) };
    }
    const op = x.ops[0];
    if (c.t === "feld") {   // Wert links
      if (op === "in" || op === "not in") {
        return typ(c.name) === "tags" ? { feld: c.name, op: op === "in" ? "hat" : "hat_nicht", wert: wertText(a) }
          : { feld: c.name, op: op === "in" ? "enthaelt" : "enthaelt_nicht", wert: wertText(a) };
      }
      const flip = { "<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!=" }[op];
      return blatt({ t: "kette", terme: [c, a], ops: [flip] });
    }
    if (a.t !== "feld" || (c.t === "liste" && typ(a.name) !== "datum")) return null;
    const t = typ(a.name);
    if (t === "datum") {
      if (c.t !== "zeit") return null;
      return { feld: a.name, op: { "==": "in", "!=": "not in" }[op] || op, wert: wertText(c) };
    }
    if (op === "is" || op === "is not") return { feld: a.name, op: op === "is" ? "leer" : "nicht_leer" };
    if (t === "text") return { feld: a.name, op: op === "==" ? "ist" : "ist_nicht", wert: wertText(c) };
    return { feld: a.name, op, wert: wertText(c) };
  };
  const pruefe = (z) => z && z.op && (z._ok === undefined || z._ok) && (OPS[typ(z.feld)] || []).some(([o]) => o === z.op);
  const gruppe = (x) => {
    if (x.t === "und" || x.t === "oder") {
      const teile = x.teile.map(blatt);
      return teile.every(pruefe) ? { verkn: x.t === "und" ? "and" : "or", teile } : null;
    }
    const z = blatt(x);
    return pruefe(z) ? z : null;
  };
  if (b.t === "und" || b.t === "oder") {
    const teile = b.teile.map(gruppe);
    return teile.every(Boolean) ? { verkn: b.t === "und" ? "and" : "or", teile } : null;
  }
  const z = gruppe(b);
  return z ? { verkn: "and", teile: [z] } : null;
}

function wertEingabe(f, z, tidBasis, aenderung) {
  const mit = (el, schl = "wert") => {
    el.addEventListener("input", () => { z[schl] = el.value; aenderung(); });
    el.addEventListener("change", () => { z[schl] = el.value; aenderung(); });
    return el;
  };
  const text = (schl = "wert", attrs = {}) => mit(h("input", { type: "text", value: z[schl] ?? "", tid: `${tidBasis}-${schl}`,
    "aria-label": schl === "wert" ? "Wert" : "bis", ...attrs }), schl);
  const auswahl = (werte, schl = "wert") => {
    const s = h("select", { tid: `${tidBasis}-${schl}`, "aria-label": "Wert" }, werte.map(([w, t]) => h("option", { value: w }, t)));
    if (z[schl] === undefined || !werte.some(([w]) => w === z[schl])) z[schl] = werte.length ? werte[0][0] : "";
    s.value = z[schl];
    return mit(s, schl);
  };
  switch (f.typ) {
    case "frei": return text("wert", { placeholder: "Suchtext" });
    case "datum": return text("wert", { class: "mono", placeholder: "z. B. 5.2.  -30d  2017  letzter_monat  1.1. .. 31.3." });
    case "text":
      return text("wert", z.op && z.op.startsWith("regex") ? { class: "mono", placeholder: "z. B. ^(rewe|edeka)\\b" } : { placeholder: "Text" });
    case "betrag": case "int": {
      if (f.name === "monat") {
        const m = MONATE.slice(1).map((x, i) => [String(i + 1), x]);
        return z.op === "zwischen" ? [auswahl(m), " und ", auswahl(m, "wert2")] : auswahl(m);
      }
      const attrs = f.typ === "betrag" ? { inputmode: "decimal", placeholder: "0,00 €" } : { inputmode: "numeric" };
      return z.op === "zwischen" ? [text("wert", attrs), " und ", text("wert2", attrs)] : text("wert", attrs);
    }
    case "auswahl": return auswahl(f.werte.map((w) => [w, w]));
    case "konto": return auswahl(baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art))).map(({ konto }) => [kontoPfad(konto), kontoPfad(konto)]));
    case "kategorie":
      return z.op === "leer" || z.op === "nicht_leer" ? null : auswahl(kategorien().map(({ konto }) => [kontoPfad(konto), kontoPfad(konto)]));
    case "tags": return auswahl(stamm.tags.slice().sort((a, b) => a.name.localeCompare(b.name, "de")).map((t) => [t.name, t.name]));
    default: return null;
  }
}

export class Baukasten {
  /** `filter`: mit Freitext und Datum, leere Zeilen werden ausgelassen (D-194). */
  constructor(sp, beiAenderung, optionen) {
    this.sp = sp;
    this.beiAenderung = beiAenderung;
    this.filter = !!(optionen && optionen.filter);
    this.felder = this.filter ? [FREITEXT, ...sp.felder] : sp.felder;
    this.modell = { verkn: "and", teile: [] };
    this.el = h("div", { class: "baukasten", tid: optionen && optionen.tid ? optionen.tid : "regel-baukasten" });
  }

  setzen(m) {
    this.modell = m || { verkn: "and", teile: [] };
    if (!this.modell.teile.length) this.modell.teile.push(this.neueZeile());
    this.zeichnen();
  }

  neueZeile() { return this.filter ? { feld: FREITEXT.name, op: "enthaelt", wert: "" } : { feld: "empfänger", op: "enthaelt", wert: "" }; }

  text() { return baukastenText(this.modell, this.sp, this.filter); }

  zeichnen() {
    let nr = 0;
    const verkn = (g, tid) => {
      const s = h("select", { tid, "aria-label": "Verknüpfung" }, h("option", { value: "and" }, "alle"),
        h("option", { value: "or" }, "mindestens eine"));
      s.value = g.verkn;
      s.addEventListener("change", () => { g.verkn = s.value; this.beiAenderung(); });
      return s;
    };
    const zeile = (z, liste) => {
      const i = nr++;
      const felder = this.felder;
      const fwahl = h("select", { tid: `bk-${i}-feld`, "aria-label": "Feld" },
        felder.map((f) => h("option", { value: f.name }, f.bezeichnung)));
      fwahl.value = z.feld;
      const f = felder.find((x) => x.name === z.feld) || felder[0];
      const ops = OPS[f.typ] || [];
      if (!ops.some(([o]) => o === z.op)) z.op = ops[0][0];
      const owahl = h("select", { tid: `bk-${i}-op`, "aria-label": "Operator" }, ops.map(([o, t]) => h("option", { value: o }, t)));
      owahl.value = z.op;
      fwahl.addEventListener("change", () => { z.feld = fwahl.value; z.wert = ""; z.wert2 = ""; this.zeichnen(); this.beiAenderung(); });
      owahl.addEventListener("change", () => { z.op = owahl.value; this.zeichnen(); this.beiAenderung(); });
      const weg = h("button", { type: "button", class: "knopf-flach", tid: `bk-${i}-weg`, "aria-label": "Bedingung entfernen",
        onclick: () => { liste.splice(liste.indexOf(z), 1); if (!this.modell.teile.length) this.modell.teile.push(this.neueZeile()); this.zeichnen(); this.beiAenderung(); } }, "×");
      return h("div", { class: "bk-zeile", tid: `bk-zeile-${i}` }, fwahl, owahl,
        h("span", { class: "bk-wert" }, wertEingabe(f, z, `bk-${i}`, () => this.beiAenderung())), weg);
    };
    const kinder = this.modell.teile.map((x) => {
      if (!x.teile) return zeile(x, this.modell.teile);
      const g = x;
      return h("div", { class: "bk-gruppe" }, h("div", { class: "bk-gruppe-kopf" }, "Gruppe: ", verkn(g, "bk-gruppe-verkn"), " der folgenden"),
        g.teile.map((z) => zeile(z, g.teile)),
        knopf("+ Bedingung", { class: "knopf klein", onclick: () => { g.teile.push(this.neueZeile()); this.zeichnen(); this.beiAenderung(); } }));
    });
    this.el.replaceChildren(
      h("p", { class: "bk-kopf" }, "Trifft zu, wenn ", verkn(this.modell, "bk-verkn"), " der folgenden Bedingungen erfüllt sind:"),
      ...kinder,
      knopfLeiste(knopf("+ Bedingung", { tid: "bk-plus", onclick: () => { this.modell.teile.push(this.neueZeile()); this.zeichnen(); this.beiAenderung(); } }),
        knopf("+ Gruppe", { tid: "bk-gruppe-plus", onclick: () => {
          this.modell.teile.push({ verkn: this.modell.verkn === "and" ? "or" : "and", teile: [this.neueZeile(), this.neueZeile()] });
          this.zeichnen();
          this.beiAenderung();
        } })));
  }
}

// ------------------------------------------------------------------ Regeleditor (5.2)
/**
 * Öffnet den Regeleditor. `r`: bestehende Regel (mit id), Vorlage ohne id (Duplizieren, „Als Regel speichern“) oder
 * null.
 */
export async function regelEditor(r, ausloeser) {
  const sp = await sprache("regel");
  const gespeichert = r && r.id ? r : null;
  dialog("regel-dialog", gespeichert ? `Regel „${r.name}“` : "Regel anlegen", (inhalt, d) => {
    const name = h("input", { type: "text", maxlength: "200", tid: "regel-name", value: r ? r.name : "" });
    // Kategorie optional (D-215). Vorgabe wie bisher die erste Kategorie; „keine“ nur bei Regeln, die nur Tags vergeben.
    const alleKat = kategorien();
    const ohneKat = !!(r && !r.kategorie_id && (r.tag_ids || []).length);
    const gewaehlt = r && r.kategorie_id ? r.kategorie_id : (ohneKat || !alleKat.length ? null : alleKat[0].konto.id);
    const kat = h("select", { tid: "regel-kategorie" }, h("option", { value: "", selected: gewaehlt === null }, "– keine Kategorie –"),
      alleKat.map(({ konto }) => h("option", { value: String(konto.id), selected: konto.id === gewaehlt }, kontoPfad(konto))));
    const tags = new TagFeld(r ? r.tag_ids || [] : [], () => { geaendert = true; vorschlagZeigen(); testPlanen(); });
    const aktiv = h("input", { type: "checkbox", tid: "regel-aktiv", checked: r ? r.aktiv !== false : true });
    const prio = h("input", { type: "number", step: "1", min: "0", tid: "regel-prioritaet",
      value: gespeichert ? String(r.prioritaet) : "" , placeholder: "am Ende" });
    let modus = modusLesen();
    let geaendert = false;
    const ausdruckEl = new AusdruckEingabe({ kontext: "regel", zeilen: 4, tid: "regel-ausdruck",
      wert: r ? (r.ausdruck || "") : "",
      beschriftung: "Bedingungen (Ausdruck)",
      platzhalter: '"REWE" in empf and dir == "ausgabe"',
      beiErgebnis: (e) => { umschalterPruefen(e); testNachPruefung(e); } });
    const baukasten = new Baukasten(sp, () => {
      const t = baukasten.text();
      vorschau.replaceChildren(t ? hervorgehoben(t, feldMenge(sp)) : h("span", { class: "klein" }, "(unvollständig)"));
      if (t !== null && t !== ausdruckEl.wert) { ausdruckEl.wert = t; test.veraltet(); }
      else if (t === null) test.veraltet("Baukasten unvollständig – Ergebnis vom letzten vollständigen Stand");
      geaendert = true;
    });
    const vorschau = h("div", { class: "bk-vorschau", tid: "regel-baukasten-ausdruck" });
    const kopierKnopf = () => knopf("Kopieren", { class: "knopf klein", tid: "regel-ausdruck-kopieren", onclick: async () => {
      melde("hinweis", (await kopieren(ausdruckEl.wert)) ? "Ausdruck kopiert." : "Kopieren ist hier nicht möglich; bitte markieren und Strg+C.");
    } });
    const tabBk = h("button", { type: "button", role: "tab", tid: "regel-modus-baukasten", class: "reiter" }, "Baukasten");
    const tabAz = h("button", { type: "button", role: "tab", tid: "regel-modus-ausdruck", class: "reiter" }, "Ausdruck");
    const bkHinweis = h("p", { class: "klein hinweis", tid: "regel-baukasten-hinweis", hidden: true });
    const bkBereich = h("div", { role: "tabpanel", class: "bk-bereich" }, baukasten.el, h("div", { class: "bk-unten" }, h("span", { class: "klein" }, "Ausdruck: "), vorschau, kopierKnopf()));
    const azBereich = h("div", { role: "tabpanel", class: "az-bereich" }, ausdruckFeld(
      "Bedingungen (Ausdruck; die alte Zeilenform „empfaenger enthaelt Bäckerei“ geht weiterhin)", ausdruckEl),
      h("p", { class: "klein" }, "Python-Ausdrücke: ", h("code", null, "and or not in == != < <= > >= is None"),
        ", Methoden ", h("code", null, '.startswith("…") .endswith("…") .search(r"…")'), ". Kurzformen: ",
        h("code", null, "empf vwz bet dir"), ". Regeln kennen kein Datum; dafür monatstag, monat, wochentag."),
      knopfLeiste(kopierKnopf()));
    // Beim Tippen nur den Reiter sperren (mit Tooltip); der Hinweistext erscheint erst beim Versuch umzuschalten,
    // damit links nichts springt (D-192).
    const umschalterPruefen = (e) => {
      const ok = !e || (e.gueltig && e.baukasten_faehig);
      tabBk.disabled = !ok && modus === "ausdruck";
      tabBk.title = ok ? "" : (e && !e.gueltig ? "Erst den Ausdruck korrigieren" : "Ausdruck zu verschachtelt für den Baukasten");
      if (ok) bkHinweis.hidden = true;
      bkHinweis.textContent = e && !e.gueltig ? "Der Ausdruck ist ungültig; im Baukasten geht es erst nach der Korrektur weiter."
        : "Dieser Ausdruck ist zu verschachtelt für den Baukasten. Bearbeiten Sie ihn als Text.";
    };
    const zeigen = async (m) => {
      if (m === "baukasten") {
        const e = ausdruckEl.wert.trim() ? await ausdruckEl.pruefen() : null;
        if (e && (!e.gueltig || !e.baukasten_faehig)) { umschalterPruefen(e); bkHinweis.hidden = false; return; }
        baukasten.setzen(e ? baukastenAusBaum(e.baum, sp) : null);
        if (e && !baukastenAusBaum(e.baum, sp)) {
          bkHinweis.hidden = false;
          bkHinweis.textContent = "Dieser Ausdruck passt nicht in den Baukasten. Bearbeiten Sie ihn als Text.";
          return;
        }
        const t = baukasten.text();
        vorschau.replaceChildren(t ? hervorgehoben(t, feldMenge(sp)) : "");
      }
      modus = m;
      modusSchreiben(m);
      bkBereich.hidden = m !== "baukasten";
      azBereich.hidden = m !== "ausdruck";
      tabBk.setAttribute("aria-selected", String(m === "baukasten"));
      tabAz.setAttribute("aria-selected", String(m === "ausdruck"));
      tabBk.disabled = false;
    };
    tabBk.addEventListener("click", () => zeigen("baukasten"));
    tabAz.addEventListener("click", () => zeigen("ausdruck"));

    // ---------------------------------------------------------- Testbereich (5.3)
    const bedingungSetzen = async (text, katId) => {
      ausdruckEl.wert = text;
      if (katId) kat.value = String(katId);
      geaendert = true;
      if (modus === "baukasten") await zeigen("baukasten");
      testPlanen();
    };
    const test = new Testbereich(() => ({ ausdruck: ausdruckEl.wert, ergebnis: ausdruckEl.ergebnis,
      kategorie_id: Number(kat.value), tag_ids: tags.ids(), tags_neu: tags.neue(),
      regel_id: gespeichert ? gespeichert.id : undefined, geaendert }),
    async () => anwendenDialog(), (text) => bedingungSetzen(text));
    // Bestehende Regel in Bedingung und Test übernehmen
    const uebernehmen = h("select", { tid: "regel-uebernehmen", "aria-label": "Bedingung einer bestehenden Regel übernehmen" },
      h("option", { value: "" }, "Bedingung einer bestehenden Regel übernehmen …"));
    api("GET", "/api/regeln").then((liste) => {
      for (const x of liste) if (!gespeichert || x.id !== gespeichert.id) uebernehmen.append(h("option", { value: String(x.id) }, x.name));
      uebernehmen.hidden = uebernehmen.options.length < 2;
      uebernehmen._regeln = liste;
    }).catch(() => { uebernehmen.hidden = true; });
    uebernehmen.addEventListener("change", () => {
      const x = (uebernehmen._regeln || []).find((y) => String(y.id) === uebernehmen.value);
      uebernehmen.value = "";
      if (x) bedingungSetzen(x.ausdruck, x.kategorie_id);
    });
    let testUhr;
    const testPlanen = () => { clearTimeout(testUhr); test.veraltet(); testUhr = setTimeout(() => test.laden(), 150); };
    // Nach jeder Prüfung sofort testen; ungültig → letztes Ergebnis bleibt sichtbar, als veraltet markiert (D-192)
    const testNachPruefung = (e) => {
      vorschlagZeigen();
      clearTimeout(testUhr);
      if (e && !e.gueltig) test.veraltet("Ausdruck ungültig – Ergebnis vom letzten gültigen Stand");
      else test.laden();
    };
    ausdruckEl.eingabe.addEventListener("input", () => test.veraltet());
    kat.addEventListener("change", () => { geaendert = true; testPlanen(); });
    ausdruckEl.eingabe.addEventListener("input", () => { geaendert = true; });

    const koerper = () => {
      const alt = alteBedingungen(ausdruckEl.wert);
      const body = { name: name.value.trim(), kategorie_id: kat.value ? Number(kat.value) : null, aktiv: aktiv.checked,
        tag_ids: tags.ids() };
      if (prio.value !== "") body.prioritaet = Number(prio.value);
      if (alt) {   // alte Zeilenform weiter annehmen (Kompatibilität mit dem bisherigen Dialog)
        body.bedingungen = alt.map(([f, o, w]) => (f === "betrag" ? { feld: f, operator: o, wert: betragLesen(w) }
          : f === "konto_id" ? { feld: f, operator: o, wert: Number(w) } : { feld: f, operator: o, wert: w }));
      } else body.ausdruck = ausdruckEl.wert;
      return body;
    };
    const vorschlag = () => {
      const k = stamm.konten.find((x) => String(x.id) === kat.value);
      return namensVorschlag(alteBedingungen(ausdruckEl.wert) ? "" : ausdruckEl.wert,
        k ? k.name : tags.namen().map((n) => `#${n}`).join(" "));
    };
    const vorschlagZeigen = () => { name.placeholder = vorschlag(); };
    ausdruckEl.eingabe.addEventListener("input", vorschlagZeigen);
    kat.addEventListener("change", vorschlagZeigen);
    vorschlagZeigen();
    name.addEventListener("input", () => name.removeAttribute("aria-invalid"));
    /** Eingaben, die der Server nur allgemein ablehnen würde, vorher am Feld melden (D-214). */
    const eingabenPruefen = () => {
      vorschlagZeigen();
      for (const el of [name, kat]) el.removeAttribute("aria-invalid");
      tags.uebernehmen();   // ein getippter, noch nicht hinzugefügter Tag zählt mit
      if (!kat.value && !tags.namen().length) {
        kat.setAttribute("aria-invalid", "true");
        kat.focus();
        throw new Error("Die Regel braucht eine Kategorie oder mindestens einen Tag.");
      }
      if (!name.value.trim()) name.value = vorschlag();   // leerer Name: Vorschlag aus Bedingung und Kategorie
      if (!name.value.trim()) {
        name.setAttribute("aria-invalid", "true");
        name.focus();
        throw new Error("Bitte einen Namen für die Regel eingeben.");
      }
    };
    const speichernUnd = async (danach) => {
      eingabenPruefen();
      // Neue Tags entstehen erst beim Speichern, in derselben Aktion (ein Rückgängig-Schritt).
      const neu = await aktion(async () => {
        await tags.anlegen();
        const body = koerper();
        return gespeichert ? api("PATCH", `/api/regeln/${gespeichert.id}`, body) : api("POST", "/api/regeln", body);
      }, { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Regel gespeichert." });
      if (danach && neu) await danach(neu);
    };
    const speichern = knopf("Speichern", { class: "knopf knopf-haupt", tid: "regel-speichern" });
    speichern.addEventListener("click", () => imDialog(d, speichern, () => speichernUnd(null)));
    const speichernAnwenden = knopf("Speichern und anwenden…", { tid: "regel-speichern-anwenden" });
    speichernAnwenden.addEventListener("click", () => imDialog(d, speichernAnwenden, () => speichernUnd((neu) =>
      anwendenFrage(neu, test, ausloeser))));
    const anwendenDialog = async () => {
      if (!gespeichert || geaendert) { speichernAnwenden.click(); return; }
      d.schliessen(true);
      await anwendenFrage(gespeichert, test, ausloeser);
    };

    const links = h("div", { class: "regel-editor-links" },
      h("div", { class: "formular-zeile" }, feld("Name", name), h("label", { class: "wahl" }, aktiv, " aktiv")),
      h("h3", null, "Wenn"), uebernehmen,
      h("div", { role: "tablist", class: "reiter-leiste", "aria-label": "Eingabeart" }, tabBk, tabAz), bkHinweis, bkBereich, azBereich,
      h("h3", null, "Dann"),
      feld("Kategorie", kat, "wird als Vorschlag gesetzt, bis er bestätigt ist"),
      tags.el,
      h("details", { class: "klein" }, h("summary", null, "Weitere Einstellungen"), feld("Priorität", prio, "kleiner = früher; leer = ans Ende")),
      knopfLeiste(speichern, speichernAnwenden, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
    inhalt.append(h("div", { class: "regel-editor" }, links, test.el));
    zeigen(modus === "baukasten" && r && r.ausdruck_form === "bedingungen" ? "baukasten" : modus);
    if (!r || !r.ausdruck) testPlanen();
    setTimeout(() => name.focus(), 0);
  }, { ausloeser, klasse: "dialog-breit dialog-regel" });
}

// ------------------------------------------------------------------ Tags einer Regel (D-215)
const tagName = (id) => (stamm.tags.find((t) => t.id === id) || {}).name || `#${id}`;
const gleichName = (a, b) => a.trim().toLocaleLowerCase("de") === b.trim().toLocaleLowerCase("de");

/** Tags, die die Regel hinzufügt: Auswahl vorhandener Tags und neue Namen. Neue Tags entstehen erst mit
 *  `anlegen()` beim Speichern der Regel; Abbrechen legt nichts an. */
class TagFeld {
  constructor(tagIds, geaendert) {
    this.geaendert = geaendert;
    this.liste = tagIds.map((id) => ({ id, name: tagName(id) }));   // {id | null, name}
    const listeId = neueId("regel-tags");
    this.eingabe = h("input", { type: "text", tid: "regel-tag-eingabe", list: listeId, autocomplete: "off", maxlength: "200",
      placeholder: "Tag wählen oder neuen Namen eingeben" });
    this.chips = h("span", { class: "regel-tags", tid: "regel-tags", role: "list", "aria-label": "Tags der Regel" });
    const hinzu = knopf("Hinzufügen", { class: "knopf klein", tid: "regel-tag-hinzufuegen", onclick: () => { this.uebernehmen(); this.eingabe.focus(); } });
    this.eingabe.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); this.uebernehmen(); }
      else if (e.key === "Backspace" && !this.eingabe.value && this.liste.length) this.entfernen(this.liste[this.liste.length - 1]);
    });
    this.el = h("div", { class: "feld" }, h("label", { for: (this.eingabe.id = neueId("regel-tag")) }, "Tags hinzufügen"),
      this.chips, h("div", { class: "regel-tag-zeile" }, this.eingabe, hinzu),
      h("datalist", { id: listeId }, stamm.tags.map((t) => h("option", { value: t.name }))),
      h("small", { class: "hinweis" }, "werden sofort an jede passende Buchung gehängt; vorhandene Tags bleiben. Unbekannte Namen legt die Regel beim Speichern als neue Tags an."));
    this.zeichnen();
  }

  ids() { return this.liste.filter((t) => t.id !== null).map((t) => t.id); }

  neue() { return this.liste.filter((t) => t.id === null).map((t) => t.name); }

  namen() { return this.liste.map((t) => t.name); }

  /** Übernimmt den getippten Namen als Tag der Regel (vorhandener Tag oder neuer Name). */
  uebernehmen() {
    const n = this.eingabe.value.trim();
    this.eingabe.value = "";
    if (!n || this.liste.some((t) => gleichName(t.name, n))) return;
    if (this.liste.length >= 20) { melde("hinweis", "Eine Regel vergibt höchstens 20 Tags."); return; }
    const t = stamm.tags.find((x) => gleichName(x.name, n));
    this.liste.push(t ? { id: t.id, name: t.name } : { id: null, name: n });
    this.zeichnen();
    this.geaendert();
  }

  entfernen(t) {
    this.liste = this.liste.filter((x) => x !== t);
    this.zeichnen();
    this.geaendert();
  }

  zeichnen() {
    this.chips.replaceChildren(...this.liste.map((t) => h("span", { class: "tag regel-tag", role: "listitem", "data-neu": String(t.id === null) },
      t.name, t.id === null ? h("em", null, " (neu)") : null,
      h("button", { type: "button", class: "regel-tag-weg", "aria-label": `Tag ${t.name} entfernen`, tid: `regel-tag-entfernen-${t.name}`,
        onclick: () => this.entfernen(t) }, "×"))));
  }

  /** Legt die neuen Tags an (innerhalb der Speichern-Aktion). */
  async anlegen() {
    for (const t of this.liste) {
      if (t.id === null) t.id = (await api("POST", "/api/tags", { name: t.name })).id;
    }
  }
}

// ------------------------------------------------------------------ Testbereich
const ZEITRAEUME = [
  { kurz: "12m", text: "12 Monate", filter: "datum in -12m" },
  { kurz: "jahr", text: "dieses Jahr", filter: "datum in dieses_jahr" },
  { kurz: "vorjahr", text: "Vorjahr", filter: "datum in vorjahr" },
  { kurz: "alle", text: "alle", filter: "" },
];

/** Namensvorschlag aus Bedingung und Kategorie, z. B. „REWE → Lebensmittel“ (Konzept 3). */
export function namensVorschlag(ausdruck, kategorie) {
  const m = /(["'])((?:\\.|(?!\1)[^\\])+)\1/.exec(ausdruck || "");
  const text = m ? m[2].replace(/\\(.)/g, "$1").trim().slice(0, 60) : "";
  return [text, kategorie || ""].filter(Boolean).join(" → ");
}

class Testbereich {
  constructor(regel, anwenden, alsBedingung) {
    this.regel = regel;
    this.alsBedingung = alsBedingung;
    this.wirkung = "";
    this.zaehlung = null;
    this.nr = 0;
    this.zeitraum = ZEITRAEUME[0];   // Zeitraum der getesteten Buchungen; die Bedingung selbst filtert (D-214)
    this.zahlenEl = h("span", { tid: "test-zahlen" });
    this.statusEl = h("span", { class: "test-status", tid: "test-status" });
    this.chipsEl = h("div", { class: "test-chips", role: "group", "aria-label": "Nach Wirkung filtern" });
    this.listeEl = h("ul", { class: "test-liste", tid: "test-liste" });
    this.erfasstEl = h("p", { class: "klein", tid: "test-nicht-erfasst" });
    this.anwendenKnopf = knopf("Anwenden…", { tid: "regel-test-anwenden", disabled: true, onclick: () => anwenden() });
    this.konto = h("select", { tid: "regel-test-konto" }, h("option", { value: "" }, "– alle Konten –"),
      baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art))).map(({ konto }) => h("option", { value: String(konto.id) }, kontoPfad(konto))));
    this.konto.addEventListener("change", () => this.laden());
    this.leerHinweis = h("p", { class: "hinweis klein", tid: "test-leer", hidden: true }, "In diesem Zeitraum gibt es keine Buchungen. ",
      knopf("Alle Buchungen testen", { class: "knopf klein", tid: "test-alle", onclick: () => this.zeitraumSetzen(ZEITRAEUME[3]) }));
    this.zeitraumChips = ZEITRAEUME.map((z) => knopf(z.text, { class: "chip", tid: `test-zeitraum-${z.kurz}`,
      "aria-pressed": String(z === this.zeitraum), onclick: () => this.zeitraumSetzen(z) }));
    this.el = h("section", { class: "regel-test", tid: "regel-test", "aria-label": "Test" },
      h("h3", null, "Test an vorhandenen Buchungen"),
      feld("Quellkonto", this.konto),
      h("div", { class: "test-schnell", role: "group", "aria-label": "Zeitraum der getesteten Buchungen" }, this.zeitraumChips),
      h("div", { class: "test-zahlen", role: "status" }, this.zahlenEl, this.statusEl), this.leerHinweis, this.chipsEl, this.listeEl, this.erfasstEl, knopfLeiste(this.anwendenKnopf));
  }

  testmengeText() { return this.zeitraum.filter; }

  zeitraumSetzen(z) {
    this.zeitraum = z;
    this.zeitraumChips.forEach((c, i) => c.setAttribute("aria-pressed", String(ZEITRAEUME[i] === z)));
    this.laden();
  }

  kontoId() { return this.konto.value ? Number(this.konto.value) : undefined; }

  planen() { clearTimeout(this.uhr); this.veraltet(); this.uhr = setTimeout(() => this.laden(), 300); }

  /** Ergebnis gilt nicht mehr für die aktuelle Eingabe: abgeblendet, mit Hinweis (D-192). */
  veraltet(text) {
    this.el.dataset.veraltet = "ja";
    this.statusEl.textContent = text || "aktualisiere …";
  }

  async laden() {
    const r = this.regel();
    const nr = ++this.nr;
    const alt = alteBedingungen(r.ausdruck);
    const leer = (text) => {
      this.zahlenEl.textContent = text;
      this.listeEl.replaceChildren();
      this.chipsEl.replaceChildren();
      this.erfasstEl.textContent = "";
      this.anwendenKnopf.disabled = true;
    };
    const ohne = !r.ausdruck.trim();   // ohne Bedingung: Buchungen der Testmenge zeigen (Bedingung „True“)
    if (alt && !(r.regel_id && !r.geaendert)) { leer("Alte Zeilenform: zum Testen speichern oder als Ausdruck schreiben."); return; }
    if (!ohne && !alt && r.ergebnis && !r.ergebnis.gueltig) {
      if (!this.listeEl.children.length) leer("Erst einen gültigen Ausdruck eingeben.");
      this.veraltet("Ausdruck ungültig – Ergebnis vom letzten gültigen Stand");
      return;
    }
    // Ohne (gültige) Kategorie läuft der Test trotzdem und zeigt die Treffer (D-214).
    const body = { kategorie_id: ohne ? undefined : r.kategorie_id || null, tag_ids: ohne ? undefined : r.tag_ids || [],
      testmenge: this.zeitraum.filter, pro_seite: 100, konto_id: this.kontoId() };
    this.tagsNeu = ohne ? [] : r.tags_neu || [];
    if (ohne) body.ausdruck = "True";
    else if (!alt) body.ausdruck = r.ausdruck;
    if (r.regel_id && !ohne) body.regel_id = r.regel_id;
    if (this.wirkung && !ohne) body.wirkung = this.wirkung;
    this.el.dataset.geladen = "nein";
    if (!this.statusEl.textContent) this.veraltet();
    let t;
    try { t = await api("POST", "/api/regeln/test", body); } catch (e) {
      if (nr === this.nr) {   // kein altes Ergebnis unter einer neuen Eingabe stehen lassen (D-214)
        leer(`Test nicht möglich: ${fehlerText(e)}`);
        this.zahlenEl.dataset.anzahl = "";
        this.leerHinweis.hidden = true;
        this.el.dataset.veraltet = "nein";
        this.statusEl.textContent = "";
        this.el.dataset.geladen = "ja";
      }
      return;
    }
    if (nr !== this.nr) return;
    this.el.dataset.veraltet = "nein";
    this.statusEl.textContent = "";
    this.zaehlung = t.zaehlung;
    this.leerHinweis.hidden = t.testmenge_anzahl > 0;
    this.ohneBedingung = ohne;
    this.zahlenEl.textContent = ohne
      ? `Noch keine Bedingung – ${t.testmenge_anzahl} Buchungen (${this.zeitraum.text}). „→ Bedingung“ übernimmt eine Buchung als Vorlage.`
      : `${t.anzahl} Treffer in ${t.testmenge_anzahl} Buchungen (${this.zeitraum.text})`;
    this.zahlenEl.dataset.anzahl = String(t.anzahl);
    this.chipsEl.replaceChildren(...(ohne ? [] : [["", "Alle", t.anzahl], ...Object.entries(t.zaehlung).filter(([, n]) => n > 0)
      .map(([w, n]) => [w, WIRKUNG_TEXT[w], n])].map(([w, text, n]) => h("button", { type: "button", class: "chip",
      tid: `test-wirkung-${w || "alle"}`, "data-anzahl": String(n), "aria-pressed": String(this.wirkung === w),
      onclick: () => { this.wirkung = w; this.laden(); } }, `${text} ${n}`))));
    this.listeEl.replaceChildren(...t.treffer.map((z) => this.zeile(z)),
      t.gesamt > t.treffer.length ? h("li", { class: "klein" }, `… und ${t.gesamt - t.treffer.length} weitere`) : "");
    const ne = t.nicht_erfasst.anzahl;
    this.erfasstEl.textContent = ne && r.kategorie_id
      ? `Nicht erfasst: ${ne} Buchung(en) haben „${pfadVon(r.kategorie_id)}“, treffen aber nicht.` : "";
    // D-246: n = Buchungen, deren Kategorie mit der Vorgabe gesetzt wird (nur „neu“); abweichende bietet das Fenster an
    const wirksam = t.zaehlung.neu || 0;
    const abweichend = t.zaehlung.abweichend || 0;
    // Neu anzulegende Tags fehlen jeder nicht gesperrten Buchung.
    const mitTags = this.tagsNeu.length ? t.anzahl - (t.gesperrt_anzahl || 0) : t.tags_anzahl || 0;
    this.tagsAnzahl = mitTags;
    this.zahlenEl.dataset.tags = String(mitTags);
    this.anwendenKnopf.disabled = ohne || !(wirksam || abweichend || mitTags);
    const hatTags = (r.tag_ids || []).length || this.tagsNeu.length;
    this.anwendenKnopf.textContent = !hatTags ? `Auf ${wirksam} Buchung(en) anwenden…`
      : r.kategorie_id ? `Anwenden: ${wirksam} × Kategorie, ${mitTags} × Tags…` : `Tags an ${mitTags} Buchung(en) vergeben…`;
    this.el.dataset.geladen = "ja";
  }

  /** Kompakte Trefferzeile (D-193): Datum, Empfänger, Betrag, Wirkung in einer Zeile; Klick klappt die Einzelheiten
   *  (Verwendungszweck, Kategorie, „→ Bedingung“, „Warum?“) auf. */
  zeile(z) {
    const vorher = z.kategorie_vorher ? pfadVon(z.kategorie_vorher) : "—";
    const nachher = z.kategorie_nachher ? pfadVon(z.kategorie_nachher) : "";
    const katText = this.ohneBedingung ? vorher : z.wirkung === "verdeckt" ? `verdeckt durch „${z.verdeckt_von.name}“`
      : z.wirkung === "uebersprungen" ? (z.grund === "gesperrt" ? "gesperrt" : "Splitbuchung") : `${vorher}${nachher ? ` → ${nachher}` : ""}`;
    const warum = h("div", { class: "test-warum", hidden: true });
    const gesperrt = z.wirkung === "uebersprungen" && z.grund === "gesperrt";
    const tagsDazu = [...(z.tags_neu || []).map(tagName), ...(gesperrt ? [] : this.tagsNeu || [])];
    const details = h("div", { class: "test-details", hidden: true, id: neueId("test-details") },
      h("div", { class: "test-zweck" }, markiert(z.verwendungszweck || "–", z.markierungen, "verwendungszweck")),
      h("div", { class: "test-kat" }, katText),
      tagsDazu.length ? h("div", { class: "test-tags" }, "Tags: ", tagsDazu.map((n) => h("span", { class: "tag" }, `+ ${n}`))) : null,
      knopfLeiste(
        knopf("→ Bedingung", { class: "knopf klein", tid: `test-uebernehmen-${z.buchung_id}`,
          title: "Empfänger dieser Buchung als Bedingung der Regel übernehmen", onclick: () => this.alsBedingung(bedingungAus(z)) }),
        this.ohneBedingung ? null : knopf("Warum?", { class: "knopf klein", tid: `test-warum-${z.buchung_id}`, onclick: () => this.warum(z.buchung_id, warum) })),
      warum);
    const kopf = h("button", { type: "button", class: "test-kopf", tid: `test-zeile-${z.buchung_id}`, "aria-expanded": "false",
      "aria-controls": details.id, title: z.verwendungszweck || "" },
    h("span", { class: "test-datum" }, datumText(z.datum)),
    h("span", { class: "test-empf" }, markiert(z.empfaenger || z.verwendungszweck || "–", z.markierungen,
      z.empfaenger ? "empfänger" : "verwendungszweck")),
    betragEl("span", z.betrag, { class: "test-betrag" }),
    this.ohneBedingung ? h("span", { class: "test-wirkung test-kat-kurz" }, vorher)
      : h("span", { class: `test-wirkung wirkung-${z.wirkung}`, "data-tags": String(tagsDazu.length) },
        z.wirkung === "treffer" && tagsDazu.length ? `+ ${tagsDazu.join(", ")}` : WIRKUNG_TEXT[z.wirkung]));
    kopf.addEventListener("click", () => {
      const auf = details.hidden;
      details.hidden = !auf;
      kopf.setAttribute("aria-expanded", String(auf));
    });
    return h("li", { class: "test-zeile", tid: `test-treffer-${z.buchung_id}`, "data-wirkung": z.wirkung }, kopf, details);
  }


  async warum(id, el) {
    if (!el.hidden) { el.hidden = true; return; }
    const r = this.regel();
    try {
      const e = await api("POST", "/api/regeln/erklaeren", { ausdruck: r.ausdruck, buchung_id: id });
      el.replaceChildren(erklaerungEl(e.baum));
      el.hidden = false;
    } catch (f) { melde("fehler", f.message); }
  }
}

/** Vorlage einer Bedingung aus einer Buchung: Empfänger, sonst der Verwendungszweck; dazu die Richtung. */
function bedingungAus(z) {
  const richtung = z.betrag < 0 ? "ausgabe" : "einnahme";
  const q = (s) => JSON.stringify(String(s));
  if (z.empfaenger) return `empf == ${q(z.empfaenger)} and dir == "${richtung}"`;
  const wort = (z.verwendungszweck || "").split(/\s+/).find((w) => w.length >= 4 && !/^\d+$/.test(w)) || z.verwendungszweck;
  return `${q(wort)} in vwz and dir == "${richtung}"`;
}

/** „Warum?“-Baum: ✓/✗ je Bedingung mit tatsächlichem Wert; nicht ausgewertete Zweige grau. */
export function erklaerungEl(k) {
  const zeichen = { wahr: "✓", falsch: "✗", nicht_ausgewertet: "–" }[k.ergebnis];
  const kopf = h("div", { class: `erk-knoten erk-${k.ergebnis}` }, h("span", { class: "erk-zeichen", "aria-label": k.ergebnis.replace("_", " ") }, zeichen), " ",
    k.kinder ? h("strong", null, { und: "alle:", oder: "mindestens eine:", nicht: "nicht:" }[k.art] || "") : h("code", null, k.text),
    k.wert !== undefined ? h("span", { class: "klein" }, ` – Wert: ${k.wert}`) : "");
  return k.kinder ? h("div", { class: "erk-gruppe" }, kopf, h("div", { class: "erk-kinder" }, k.kinder.map(erklaerungEl))) : kopf;
}

/** Rückfrage „Auf n Buchungen anwenden“ (5.3) und POST /api/regeln/{id}/anwenden. */
async function anwendenFrage(regel, test, ausloeser) {
  const testmenge = test.testmengeText();
  const kontoId = test.kontoId();
  const zaehlung = test.zaehlung;
  const neu = zaehlung ? zaehlung.neu || 0 : null;
  const abw = zaehlung ? zaehlung.abweichend || 0 : null;
  const mitKat = !!regel.kategorie_id;
  const tags = regel.tag_ids || [];
  const mitTags = zaehlung ? test.tagsAnzahl || 0 : null;
  dialog("regel-anwenden-dialog", `Regel „${regel.name}“ anwenden`, (inhalt, d) => {
    const ueber = h("input", { type: "checkbox", tid: "regel-anwenden-abweichende" });
    const ok = knopf("Anwenden", { class: "knopf knopf-haupt", tid: "regel-anwenden-ok" });
    ok.addEventListener("click", () => imDialog(d, ok, async () => {
      const r = await aktion(() => api("POST", `/api/regeln/${regel.id}/anwenden`,
        { testmenge, konto_id: kontoId, abweichende_ueberschreiben: ueber.checked }), { stillBeiFehler: true, danach: () => d.schliessen(true) });
      if (r) melde("erfolg", r.anzahl ? `${r.anzahl} Buchung(en) geändert. Rückgängig mit Strg+Z.` : "Keine Buchung geändert.");
    }));
    const nichts = zaehlung && !abw && !(mitKat && neu) && !(tags.length && mitTags);
    // Nur vorhandene Teile anhängen: `append(null)` schriebe das Wort „null“ in das Fenster (D-216).
    const teile = [
      h("p", { tid: "regel-anwenden-umfang" }, `Zeitraum: ${test.zeitraum.text}`,
        kontoId ? ` · Quellkonto ${pfadVon(kontoId)}` : ""),
      nichts ? h("p", { tid: "regel-anwenden-nichts" }, "In diesem Umfang ändert die Regel nichts: Es gibt keine passende Buchung, die sie noch nicht erfasst hat.") : null,
      mitKat && !nichts && neu !== 0 ? h("p", { tid: "regel-anwenden-kategorie" }, neu === null ? `Unkategorisierte Buchungen erhalten „${pfadVon(regel.kategorie_id)}“ als Vorschlag.`
        : `${neu} unkategorisierte Buchung(en) erhalten „${pfadVon(regel.kategorie_id)}“ als Vorschlag.`) : null,
      mitKat && (abw === null || abw > 0) ? h("label", { class: "wahl" }, ueber,
        abw === null ? " auch Buchungen mit anderer Kategorie überschreiben" : ` auch ${abw} Buchung(en) mit anderer Kategorie überschreiben`) : null,
      tags.length && !nichts ? h("p", { tid: "regel-anwenden-tags" }, mitTags === null ? "Passende Buchungen erhalten: " : `${mitTags} Buchung(en) erhalten: `,
        tags.map((id) => h("span", { class: "tag" }, `+ ${tagName(id)}`)), " Vorhandene Tags bleiben.") : null,
      h("p", { class: "klein" }, mitKat ? "Verdeckte und gesperrte Buchungen bleiben unverändert. Das Anwenden ist ein Schritt und lässt sich rückgängig machen."
        : "Gesperrte Buchungen bleiben unverändert. Das Anwenden ist ein Schritt und lässt sich rückgängig machen."),
      knopfLeiste(ok, knopf(nichts ? "Schließen" : "Abbrechen", { onclick: () => d.schliessen(null) })),
    ];
    ok.hidden = !!nichts;
    inhalt.append(...teile.filter(Boolean));
  }, { ausloeser });
}

export { neueId };
