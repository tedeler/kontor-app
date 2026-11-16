/* Kontor – Regelliste, Regeleditor (Baukasten und Ausdruck) und Testbereich (D-179, Konzept 5.1–5.3). */
import {
  BESTAND, aktion, api, baumFolge, betragEl, betragLesen, datumText, h, kategorien, kontoPfad, melde, neueId, pfadVon,
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
export async function regelnSeite(seite, kopf) {
  const [liste, sp] = await Promise.all([api("GET", "/api/regeln"), sprache("regel")]);
  const felder = feldMenge(sp);
  kopf(seite, "Regeln",
    knopf("Regel anlegen", { tid: "regel-anlegen", class: "knopf knopf-haupt", onclick: (e) => regelEditor(null, e.currentTarget) }),
    knopf("Regeln anwenden", { tid: "regeln-anwenden", onclick: async () => {
      try {
        const r = await aktion(() => api("POST", "/api/regeln/anwenden", {}), { erfolg: "Regeln angewendet." });
        if (r && r.anzahl !== undefined) melde("hinweis", `${r.anzahl} Buchungen geändert.`);
      } catch (e) { /* gemeldet */ }
    } }),
    knopf("Lernmodell anwenden", { onclick: async () => {
      try { await aktion(() => api("POST", "/api/lernmodell/anwenden", {}), { erfolg: "Lernmodell angewendet." }); } catch (e) { /* gemeldet */ }
    } }));
  if (!liste.length) {
    seite.append(h("p", { class: "leer" }, "Noch keine Regeln. Regeln ordnen neuen Buchungen eine Kategorie zu, bevor das Lernmodell gefragt wird."));
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
      h("strong", null, r.name), h("span", { class: "regel-ziel" }, ` → ${pfadVon(r.kategorie_id)}`),
      h("div", { class: "regel-bedingung", tid: `regel-ausdruck-${r.id}`, title: r.ausdruck }, hervorgehoben(r.ausdruck || "", felder))),
    knopfLeiste(
      knopf("Bearbeiten…", { "aria-label": `Regel ${r.name} bearbeiten`, onclick: (e) => regelEditor(r, e.currentTarget) }),
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
  seite.append(h("p", { class: "hinweis klein" }, "Regeln wirken von oben nach unten; für die Kategorie gilt die erste passende Regel. "
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
// nur im Filter (D-188): Datum mit Zeitangaben nach Konzept 4.6, Freitext wie die Volltextsuche
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
  if (leereAuslassen) {   // im Filter: leere Zeilen zählen nicht (D-188)
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
  /** `filter`: mit Freitext und Datum, leere Zeilen werden ausgelassen (D-188). */
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
 * null. Optional `r.testmenge` als Vorgabe der Testmenge.
 */
export async function regelEditor(r, ausloeser) {
  const sp = await sprache("regel");
  const gespeichert = r && r.id ? r : null;
  dialog("regel-dialog", gespeichert ? `Regel „${r.name}“` : "Regel anlegen", (inhalt, d) => {
    const name = h("input", { type: "text", maxlength: "200", tid: "regel-name", value: r ? r.name : "" });
    const kat = h("select", { tid: "regel-kategorie" }, kategorien().map(({ konto }) => h("option", { value: String(konto.id),
      selected: r && konto.id === r.kategorie_id }, kontoPfad(konto))));
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
    const testKnopf = () => knopf("Als Testmenge übernehmen", { class: "knopf klein", tid: "regel-in-testmenge",
      title: "Zeigt im Test alle Buchungen, auf die der Ausdruck passt", onclick: () => {
        if (!ausdruckEl.wert.trim()) { melde("hinweis", "Noch keine Bedingung."); return; }
        test.menge.wert = ausdruckEl.wert;
        test.laden();
      } });
    const tabBk = h("button", { type: "button", role: "tab", tid: "regel-modus-baukasten", class: "reiter" }, "Baukasten");
    const tabAz = h("button", { type: "button", role: "tab", tid: "regel-modus-ausdruck", class: "reiter" }, "Ausdruck");
    const bkHinweis = h("p", { class: "klein hinweis", tid: "regel-baukasten-hinweis", hidden: true });
    const bkBereich = h("div", { role: "tabpanel", class: "bk-bereich" }, baukasten.el, h("div", { class: "bk-unten" }, h("span", { class: "klein" }, "Ausdruck: "), vorschau, kopierKnopf(), testKnopf()));
    const azBereich = h("div", { role: "tabpanel", class: "az-bereich" }, ausdruckFeld(
      "Bedingungen (Ausdruck; die alte Zeilenform „empfaenger enthaelt Bäckerei“ geht weiterhin)", ausdruckEl),
      h("p", { class: "klein" }, "Python-Ausdrücke: ", h("code", null, "and or not in == != < <= > >= is None"),
        ", Methoden ", h("code", null, '.startswith("…") .endswith("…") .search(r"…")'), ". Kurzformen: ",
        h("code", null, "empf vwz bet dir"), ". Regeln kennen kein Datum; dafür monatstag, monat, wochentag."),
      knopfLeiste(kopierKnopf(), testKnopf()));
    // Beim Tippen nur den Reiter sperren (mit Tooltip); der Hinweistext erscheint erst beim Versuch umzuschalten,
    // damit links nichts springt (D-186).
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
      kategorie_id: Number(kat.value), regel_id: gespeichert ? gespeichert.id : undefined, geaendert }),
    r && r.testmenge, async () => anwendenDialog(), (text) => bedingungSetzen(text));
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
    // Nach jeder Prüfung sofort testen; ungültig → letztes Ergebnis bleibt sichtbar, als veraltet markiert (D-186)
    const testNachPruefung = (e) => {
      clearTimeout(testUhr);
      if (e && !e.gueltig) test.veraltet("Ausdruck ungültig – Ergebnis vom letzten gültigen Stand");
      else test.laden();
    };
    ausdruckEl.eingabe.addEventListener("input", () => test.veraltet());
    kat.addEventListener("change", () => { geaendert = true; testPlanen(); });
    ausdruckEl.eingabe.addEventListener("input", () => { geaendert = true; });

    const koerper = () => {
      const alt = alteBedingungen(ausdruckEl.wert);
      const body = { name: name.value.trim(), kategorie_id: Number(kat.value), aktiv: aktiv.checked };
      if (prio.value !== "") body.prioritaet = Number(prio.value);
      if (alt) {   // alte Zeilenform weiter annehmen (Kompatibilität mit dem bisherigen Dialog)
        body.bedingungen = alt.map(([f, o, w]) => (f === "betrag" ? { feld: f, operator: o, wert: betragLesen(w) }
          : f === "konto_id" ? { feld: f, operator: o, wert: Number(w) } : { feld: f, operator: o, wert: w }));
      } else body.ausdruck = ausdruckEl.wert;
      return body;
    };
    const speichernUnd = async (danach) => {
      const body = koerper();
      const neu = await aktion(() => (gespeichert ? api("PATCH", `/api/regeln/${gespeichert.id}`, body) : api("POST", "/api/regeln", body)),
        { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Regel gespeichert." });
      if (danach && neu) await danach(neu);
    };
    const speichern = knopf("Speichern", { class: "knopf knopf-haupt", tid: "regel-speichern" });
    speichern.addEventListener("click", () => imDialog(d, speichern, () => speichernUnd(null)));
    const speichernAnwenden = knopf("Speichern und anwenden…", { tid: "regel-speichern-anwenden" });
    speichernAnwenden.addEventListener("click", () => imDialog(d, speichernAnwenden, () => speichernUnd((neu) =>
      anwendenFrage(neu, test.testmengeText(), test.kontoId(), test.zaehlung, ausloeser))));
    const anwendenDialog = async () => {
      if (!gespeichert || geaendert) { speichernAnwenden.click(); return; }
      d.schliessen(true);
      await anwendenFrage(gespeichert, test.testmengeText(), test.kontoId(), test.zaehlung, ausloeser);
    };

    const links = h("div", { class: "regel-editor-links" },
      h("div", { class: "formular-zeile" }, feld("Name", name), h("label", { class: "wahl" }, aktiv, " aktiv")),
      h("h3", null, "Wenn"), uebernehmen,
      h("div", { role: "tablist", class: "reiter-leiste", "aria-label": "Eingabeart" }, tabBk, tabAz), bkHinweis, bkBereich, azBereich,
      h("h3", null, "Dann"),
      feld("Kategorie", kat, "wird als Vorschlag gesetzt, bis er bestätigt ist"),
      h("details", { class: "klein" }, h("summary", null, "Weitere Einstellungen"), feld("Priorität", prio, "kleiner = früher; leer = ans Ende")),
      knopfLeiste(speichern, speichernAnwenden, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
    inhalt.append(h("div", { class: "regel-editor" }, links, test.el));
    zeigen(modus === "baukasten" && r && r.ausdruck_form === "bedingungen" ? "baukasten" : modus);
    if (!r || !r.ausdruck) testPlanen();
    setTimeout(() => name.focus(), 0);
  }, { ausloeser, klasse: "dialog-breit dialog-regel" });
}

// ------------------------------------------------------------------ Testbereich
class Testbereich {
  constructor(regel, testmenge, anwenden, alsBedingung) {
    this.regel = regel;
    this.alsBedingung = alsBedingung;
    this.wirkung = "";
    this.zaehlung = null;
    this.nr = 0;
    this.menge = new AusdruckEingabe({ kontext: "filter", tid: "regel-testmenge", wert: testmenge ?? "datum in -12m",
      beschriftung: "Testmenge", beiEnter: () => this.laden(), beiErgebnis: (e) => { if (e && e.gueltig) this.planen(); } });
    this.zahlenEl = h("span", { tid: "test-zahlen" });
    this.statusEl = h("span", { class: "test-status", tid: "test-status" });
    this.chipsEl = h("div", { class: "test-chips", role: "group", "aria-label": "Nach Wirkung filtern" });
    this.listeEl = h("ul", { class: "test-liste", tid: "test-liste" });
    this.erfasstEl = h("p", { class: "klein", tid: "test-nicht-erfasst" });
    this.anwendenKnopf = knopf("Anwenden…", { tid: "regel-test-anwenden", disabled: true, onclick: () => anwenden() });
    this.konto = h("select", { tid: "regel-test-konto" }, h("option", { value: "" }, "– alle Konten –"),
      baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art))).map(({ konto }) => h("option", { value: String(konto.id) }, kontoPfad(konto))));
    this.konto.addEventListener("change", () => this.laden());
    this.leerHinweis = h("p", { class: "hinweis klein", tid: "test-leer", hidden: true }, "Die Testmenge enthält keine Buchungen. ",
      knopf("Alle Buchungen testen", { class: "knopf klein", tid: "test-alle", onclick: () => { this.menge.wert = ""; this.laden(); } }));
    const schnell = [["12 Monate", "datum in -12m"], ["dieses Jahr", "datum in dieses_jahr"], ["Vorjahr", "datum in vorjahr"], ["alle", ""]];
    this.el = h("section", { class: "regel-test", tid: "regel-test", "aria-label": "Test" },
      h("h3", null, "Test an vorhandenen Buchungen"),
      feld("Quellkonto", this.konto),
      ausdruckFeld("Testmenge (Filter)", this.menge),
      h("div", { class: "test-schnell" }, schnell.map(([t, w]) => knopf(t, { class: "chip", onclick: () => { this.menge.wert = w; this.laden(); } }))),
      h("div", { class: "test-zahlen", role: "status" }, this.zahlenEl, this.statusEl), this.leerHinweis, this.chipsEl, this.listeEl, this.erfasstEl, knopfLeiste(this.anwendenKnopf));
  }

  testmengeText() { return this.menge.wert; }

  kontoId() { return this.konto.value ? Number(this.konto.value) : undefined; }

  planen() { clearTimeout(this.uhr); this.veraltet(); this.uhr = setTimeout(() => this.laden(), 300); }

  /** Ergebnis gilt nicht mehr für die aktuelle Eingabe: abgeblendet, mit Hinweis (D-186). */
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
    const body = { kategorie_id: ohne ? undefined : r.kategorie_id, testmenge: this.menge.wert, pro_seite: 100, konto_id: this.kontoId() };
    if (ohne) body.ausdruck = "True";
    else if (!alt) body.ausdruck = r.ausdruck;
    if (r.regel_id && !ohne) body.regel_id = r.regel_id;
    if (this.wirkung && !ohne) body.wirkung = [this.wirkung];
    this.el.dataset.geladen = "nein";
    if (!this.statusEl.textContent) this.veraltet();
    let t;
    try { t = await api("POST", "/api/regeln/test", body); } catch (e) {
      if (nr === this.nr) { this.veraltet(e.message || "Test nicht möglich."); this.el.dataset.geladen = "ja"; }
      return;
    }
    if (nr !== this.nr) return;
    this.el.dataset.veraltet = "nein";
    this.statusEl.textContent = "";
    this.zaehlung = t.zaehlung;
    this.leerHinweis.hidden = t.testmenge_anzahl > 0;
    this.ohneBedingung = ohne;
    this.zahlenEl.textContent = ohne
      ? `Noch keine Bedingung – ${t.testmenge_anzahl} Buchungen der Testmenge. „→ Bedingung“ übernimmt eine Buchung als Vorlage.`
      : `${t.anzahl} Treffer in ${t.testmenge_anzahl} Buchungen der Testmenge`;
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
    const wirksam = (t.zaehlung.neu || 0) + (t.zaehlung.abweichend || 0);
    this.anwendenKnopf.disabled = ohne || !wirksam;
    this.anwendenKnopf.textContent = `Auf ${wirksam} Buchung(en) anwenden…`;
    this.el.dataset.geladen = "ja";
  }

  /** Kompakte Trefferzeile (D-187): Datum, Empfänger, Betrag, Wirkung in einer Zeile; Klick klappt die Einzelheiten
   *  (Verwendungszweck, Kategorie, „→ Bedingung“, „Warum?“) auf. */
  zeile(z) {
    const vorher = z.kategorie_vorher ? pfadVon(z.kategorie_vorher) : "—";
    const nachher = z.kategorie_nachher ? pfadVon(z.kategorie_nachher) : "";
    const katText = this.ohneBedingung ? vorher : z.wirkung === "verdeckt" ? `verdeckt durch „${z.verdeckt_von.name}“`
      : z.wirkung === "uebersprungen" ? (z.grund === "gesperrt" ? "gesperrt" : "Splitbuchung") : `${vorher}${nachher ? ` → ${nachher}` : ""}`;
    const warum = h("div", { class: "test-warum", hidden: true });
    const details = h("div", { class: "test-details", hidden: true, id: neueId("test-details") },
      h("div", { class: "test-zweck" }, markiert(z.verwendungszweck || "–", z.markierungen, "verwendungszweck")),
      h("div", { class: "test-kat" }, katText),
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
      : h("span", { class: `test-wirkung wirkung-${z.wirkung}` }, WIRKUNG_TEXT[z.wirkung]));
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
async function anwendenFrage(regel, testmenge, kontoId, zaehlung, ausloeser) {
  const neu = zaehlung ? zaehlung.neu || 0 : null;
  const abw = zaehlung ? zaehlung.abweichend || 0 : null;
  dialog("regel-anwenden-dialog", `Regel „${regel.name}“ anwenden`, (inhalt, d) => {
    const ueber = h("input", { type: "checkbox", tid: "regel-anwenden-abweichende" });
    const ok = knopf("Anwenden", { class: "knopf knopf-haupt", tid: "regel-anwenden-ok" });
    ok.addEventListener("click", () => imDialog(d, ok, async () => {
      const r = await aktion(() => api("POST", `/api/regeln/${regel.id}/anwenden`,
        { testmenge, konto_id: kontoId, abweichende_ueberschreiben: ueber.checked }), { stillBeiFehler: true, danach: () => d.schliessen(true) });
      if (r) melde("erfolg", `${r.anzahl} Buchung(en) geändert. Rückgängig mit Strg+Z.`);
    }));
    inhalt.append(h("p", null, "Testmenge: ", h("code", null, testmenge || "alle Buchungen"),
      kontoId ? ` · Quellkonto ${pfadVon(kontoId)}` : ""),
      h("p", null, neu === null ? "Unkategorisierte Buchungen erhalten einen Vorschlag." : `${neu} unkategorisierte Buchung(en) erhalten einen Vorschlag.`),
      h("label", { class: "wahl" }, ueber, ` auch abweichende überschreiben${abw === null ? "" : ` (${abw})`}`),
      h("p", { class: "klein" }, "Verdeckte und gesperrte Buchungen bleiben unverändert. Eine Änderung im Protokoll."),
      knopfLeiste(ok, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

export { neueId };
