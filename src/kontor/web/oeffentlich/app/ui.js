/* Kontor – Dialoge (oberflaeche.md 9) und Kontextmenüs (8). */
import {
  ApiFehler, BESTAND, aktion, anhaengen, api, betragEingabe, betragEl, betragLesen, betragText, datumText, ebeneOeffnen,
  ebeneSchliessen, fehlerText, h, kategorien, klasse, kontoNach, kontoPfad, baumFolge, melde, neueId, oberflaeche, passt,
  personBestaetigt, stamm, tid,
} from "./kern.js";

// ------------------------------------------------------------------ Dialog-Grundgerüst (9)
const FOKUSSIERBAR = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
  'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function fokussierbare(wurzel) {
  return [...wurzel.querySelectorAll(FOKUSSIERBAR)].filter((e) => !e.closest("[hidden]") && e.offsetParent !== null);
}

/**
 * Öffnet einen modalen Dialog. `aufbau(inhalt, d)` füllt ihn; `d.schliessen(wert)` schließt ihn und gibt den
 * Fokus an das auslösende Element zurück; `d.fehler(text)` zeigt `dialog-fehler`. Ergebnis: Promise auf den Wert
 * (Esc → null).
 */
export function dialog(testid, titel, aufbau, optionen) {
  const o = optionen || {};
  const ausloeser = o.ausloeser || document.activeElement;
  const kopfId = neueId("dialog-titel");
  const fehlerEl = h("p", { class: "dialog-fehler", tid: "dialog-fehler", role: "alert", hidden: true });
  const inhalt = h("div", { class: "dialog-inhalt" });
  const box = h("div", { class: "dialog " + (o.klasse || ""), role: "dialog", "aria-modal": "true",
    "aria-labelledby": kopfId, tid: testid },
  h("div", { class: "dialog-kopf" }, h("h2", { id: kopfId }, titel),
    o.schliessenKnopf ? h("button", { type: "button", class: "knopf-flach", tid: o.schliessenKnopf,
      "aria-label": "Schließen", onclick: () => d.schliessen(null) }, "×") : null),
  fehlerEl, inhalt);
  const huelle = h("div", { class: "dialog-huelle" }, box);
  let fertig;
  const ergebnis = new Promise((r) => { fertig = r; });
  const d = {
    art: "dialog", el: box, huelle,
    offen: true,
    schliessen(wert) {
      if (!d.offen) return;
      d.offen = false;
      ebeneSchliessen(d);
      huelle.remove();
      if (o.beimSchliessen) o.beimSchliessen();
      if (ausloeser && ausloeser.isConnected && typeof ausloeser.focus === "function") ausloeser.focus();
      fertig(wert === undefined ? null : wert);
    },
    gesperrt: false,
    escape() { if (!d.gesperrt) d.schliessen(null); },
    /** Sperrt den Dialog (alle Eingaben und Knöpfe, Esc), z. B. während eine Synchronisation läuft. */
    sperren(an) {
      d.gesperrt = !!an;
      box.setAttribute("aria-busy", an ? "true" : "false");
      box.dataset.gesperrt = an ? "ja" : "nein";
      for (const el of box.querySelectorAll("input, select, textarea, button")) {
        if (an) { if (!el.disabled) { el.disabled = true; el.dataset.gesperrtDurchDialog = "ja"; } }
        else if (el.dataset.gesperrtDurchDialog) { el.disabled = false; delete el.dataset.gesperrtDurchDialog; }
      }
    },
    fehler(text) {
      fehlerEl.textContent = text || "";
      fehlerEl.hidden = !text;
    },
    tab(e) { fokusFalle(box, e); },
    ergebnis,
  };
  aufbau(inhalt, d);
  document.body.append(huelle);
  ebeneOeffnen(d);
  let ziel = o.fokus ? o.fokus(box) : (box.querySelector("input:not([type=hidden]):not([disabled]), select, textarea")
    || box.querySelector("button:not([disabled])"));
  if (oberflaeche.istMobil && oberflaeche.istMobil()) {
    // mobil (D-141): die Bildschirmtastatur erst auf Tippen ins Feld öffnen; Tippen neben das Blatt schließt es
    if (!o.fokus && ziel && ziel.matches("input:not([type=checkbox]):not([type=radio]):not([type=date]), textarea")) {
      box.tabIndex = -1;
      ziel = box;
    }
    huelle.addEventListener("click", (e) => { if (e.target === huelle) d.escape(); });
  }
  if (ziel) ziel.focus();
  return d;
}

export function fokusFalle(box, e) {
  const f = fokussierbare(box);
  if (!f.length) { e.preventDefault(); return; }
  const i = f.indexOf(document.activeElement);
  e.preventDefault();
  const n = e.shiftKey ? (i <= 0 ? f.length - 1 : i - 1) : (i < 0 || i === f.length - 1 ? 0 : i + 1);
  f[n].focus();
}

/** Ausführen in einem Dialog: Fehler des Servers in dialog-fehler, Dialog bleibt offen. */
export async function imDialog(d, knopf, ausfuehren) {
  d.fehler("");
  if (knopf) knopf.disabled = true;
  try {
    const erg = await ausfuehren();
    return erg;
  } catch (e) {
    if (d.offen) d.fehler(fehlerText(e));
    return undefined;
  } finally {
    if (knopf && knopf.isConnected) knopf.disabled = false;
  }
}

export function feld(beschriftung, eingabe, hinweis) {
  const id = eingabe.id || neueId("feld");
  eingabe.id = id;
  return h("div", { class: "feld" }, h("label", { for: id }, beschriftung), eingabe,
    hinweis ? h("small", { class: "hinweis" }, hinweis) : null);
}

export const knopf = (text, attrs) => h("button", { type: "button", class: "knopf", ...(attrs || {}) }, text);

export function knopfLeiste(...knoepfe) {
  return h("div", { class: "knopf-leiste" }, knoepfe);
}

// ------------------------------------------------------------------ Rückfrage (9.5)
export function bestaetigen(text, optionen) {
  const o = optionen || {};
  const d = dialog("bestaetigen-dialog", o.titel || "Bitte bestätigen", (inhalt, dd) => {
    inhalt.append(h("p", null, text),
      knopfLeiste(knopf(o.ja || "Ja", { tid: "bestaetigen-ja", class: "knopf knopf-gefahr", onclick: () => dd.schliessen(true) }),
        knopf(o.nein || "Abbrechen", { tid: "bestaetigen-nein", onclick: () => dd.schliessen(false) })));
  }, { fokus: (b) => tid("bestaetigen-nein", b), ausloeser: o.ausloeser });
  return d.ergebnis.then((w) => w === true);
}

// ------------------------------------------------------------------ Kontextmenü (8)
let offenesMenue = null;

/** eintraege: [{tid, text, aktiv, tun, kinder}] – ``kinder`` öffnet ein Untermenü. */
export function kontextmenue(x, y, eintraege, ausloeser) {
  if (offenesMenue) offenesMenue.schliessen(false);
  const liste = h("div", { class: "kontextmenue", role: "menu", tid: "kontextmenue", "aria-label": "Kontextmenü",
    tabindex: "-1" });
  let unter = null;
  let unterEintraege = [];
  let unterItems = [];
  const items = eintraege.map((e) => {
    const hatKinder = !!(e.kinder && e.kinder.length);
    // D-248: Einträge mit ``an`` (true/false) sind Ankreuzeinträge mit aria-checked (E-306)
    const el = h("div", { role: e.an === undefined ? "menuitem" : "menuitemcheckbox", tid: e.tid, tabindex: "-1",
      "aria-checked": e.an === undefined ? null : String(e.an),
      class: "menue-eintrag" + (hatKinder ? " menue-mit-unter" : ""),
      "aria-disabled": e.aktiv === false ? "true" : null, "aria-haspopup": hatKinder ? "menu" : null,
      "aria-expanded": hatKinder ? "false" : null },
    h("span", { class: "menue-text" }, e.text),
    // Kürzel nur als Darstellung (CSS ::after), damit der Text des Eintrags unverändert bleibt (D-168).
    e.kuerzel && !oberflaeche.istMobil() ? h("kbd", { class: "menue-kuerzel", "aria-hidden": "true",
      "data-kuerzel": e.kuerzel }) : null,
    hatKinder ? h("span", { class: "menue-pfeil", "aria-hidden": "true" }, "›") : null);
    el.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (hatKinder) unterOeffnen(el, e);
      else ausfuehren(e);
    });
    if (hatKinder) el.addEventListener("mouseenter", () => { if (!oberflaeche.istMobil()) unterOeffnen(el, e); });
    else el.addEventListener("mouseenter", () => unterSchliessen());
    return el;
  });
  anhaengen(liste, items);
  const aktive = () => items.filter((el) => el.getAttribute("aria-disabled") !== "true");
  const m = {
    art: "menue", el: liste,
    schliessen(fokusZurueck = true) {
      if (offenesMenue !== m) return;
      unterSchliessen();
      offenesMenue = null;
      ebeneSchliessen(m);
      liste.remove();
      document.removeEventListener("pointerdown", aussen, true);
      if (fokusZurueck && ausloeser && ausloeser.isConnected) ausloeser.focus();
    },
    escape() {
      if (unter) {
        const offen = items.find((el) => el.getAttribute("aria-expanded") === "true");
        unterSchliessen();
        if (offen) offen.focus();
        return;
      }
      m.schliessen(true);
    },
  };
  function ausfuehren(e) {
    if (e.aktiv === false) return;
    m.schliessen(true);
    Promise.resolve().then(() => e.tun());
  }
  function unterSchliessen() {
    if (!unter) return;
    unter.remove();
    unter = null;
    unterEintraege = [];
    unterItems = [];
    for (const el of items) if (el.getAttribute("aria-expanded") === "true") el.setAttribute("aria-expanded", "false");
  }
  function unterOeffnen(el, e) {
    if (e.aktiv === false) return;
    if (unter && el.getAttribute("aria-expanded") === "true") return;
    unterSchliessen();
    const box = h("div", { class: "kontextmenue untermenue", role: "menu", tid: "untermenue",
      "aria-label": e.text, tabindex: "-1" });
    unterEintraege = e.kinder;
    unterItems = e.kinder.map((k) => {
      const kn = h("div", { role: k.an === undefined ? "menuitem" : "menuitemcheckbox", tid: k.tid, tabindex: "-1",
        "aria-checked": k.an === undefined ? null : String(k.an), class: "menue-eintrag",
        "aria-disabled": k.aktiv === false ? "true" : null }, k.text);
      kn.addEventListener("click", (ev) => { ev.stopPropagation(); ausfuehren(k); });
      return kn;
    });
    anhaengen(box, unterItems);
    box.addEventListener("keydown", (ev) => unterTaste(ev));
    box.addEventListener("contextmenu", (ev) => ev.preventDefault());
    document.body.append(box);
    const pr = el.getBoundingClientRect();
    const br = box.getBoundingClientRect();
    let left = pr.right + 4;
    let top = pr.top;
    if (oberflaeche.istMobil() || left + br.width > window.innerWidth - 4) left = Math.max(4, pr.left - br.width - 4);
    if (oberflaeche.istMobil()) {
      left = 8;
      box.style.width = "calc(100vw - 16px)";
      top = Math.max(4, pr.top - box.getBoundingClientRect().height - 6);
    } else if (top + br.height > window.innerHeight - 4) top = Math.max(4, window.innerHeight - br.height - 4);
    box.style.left = left + "px";
    box.style.top = top + "px";
    unter = box;
    el.setAttribute("aria-expanded", "true");
  }
  function unterTaste(ev) {
    const a = unterItems.filter((el) => el.getAttribute("aria-disabled") !== "true");
    const i = a.indexOf(document.activeElement);
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      ev.stopPropagation();
      if (!a.length) return;
      const n = ev.key === "ArrowDown" ? (i + 1) % a.length : (i - 1 + a.length) % a.length;
      a[n].focus();
    } else if (ev.key === "ArrowLeft" || ev.key === "Escape") {
      ev.preventDefault();
      ev.stopPropagation();
      const offen = items.find((el) => el.getAttribute("aria-expanded") === "true");
      unterSchliessen();
      if (offen) offen.focus();
    } else if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      ev.stopPropagation();
      const idx = unterItems.indexOf(document.activeElement);
      if (idx >= 0) ausfuehren(unterEintraege[idx]);
    } else if (ev.key === "Tab") ev.preventDefault();
  }
  function aussen(ev) {
    if (!liste.contains(ev.target) && !(unter && unter.contains(ev.target))) m.schliessen(true);
  }
  liste.addEventListener("keydown", (ev) => {
    if (unter && unter.contains(document.activeElement)) { unterTaste(ev); return; }
    const a = aktive();
    const i = a.indexOf(document.activeElement);
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      unterSchliessen();
      if (!a.length) return;
      const n = ev.key === "ArrowDown" ? (i + 1) % a.length : (i - 1 + a.length) % a.length;
      a[n].focus();
    } else if (ev.key === "ArrowRight") {
      const idx = items.indexOf(document.activeElement);
      if (idx >= 0 && eintraege[idx].kinder && eintraege[idx].kinder.length && eintraege[idx].aktiv !== false) {
        ev.preventDefault();
        unterOeffnen(items[idx], eintraege[idx]);
        const erstes = unterItems.find((el) => el.getAttribute("aria-disabled") !== "true");
        if (erstes) erstes.focus();
      }
    } else if (ev.key === "Home" || ev.key === "End") {
      ev.preventDefault();
      unterSchliessen();
      if (a.length) a[ev.key === "Home" ? 0 : a.length - 1].focus();
    } else if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      const idx = items.indexOf(document.activeElement);
      if (idx >= 0) {
        if (eintraege[idx].kinder && eintraege[idx].kinder.length) {
          unterOeffnen(items[idx], eintraege[idx]);
          const erstes = unterItems.find((el) => el.getAttribute("aria-disabled") !== "true");
          if (erstes) erstes.focus();
        } else ausfuehren(eintraege[idx]);
      }
    } else if (ev.key === "Tab") {
      ev.preventDefault();
    }
  });
  liste.addEventListener("contextmenu", (ev) => ev.preventDefault());
  document.body.append(liste);
  // vollständig im sichtbaren Bereich (8.1)
  const r = liste.getBoundingClientRect();
  const bx = Math.max(4, Math.min(x, window.innerWidth - r.width - 4));
  const by = Math.max(4, Math.min(y, window.innerHeight - r.height - 4));
  liste.style.left = bx + "px";
  liste.style.top = by + "px";
  offenesMenue = m;
  ebeneOeffnen(m);
  setTimeout(() => document.addEventListener("pointerdown", aussen, true), 0);
  const erster = aktive()[0];
  (erster || liste).focus();
  return m;
}

export function menuePosition(ev, el) {
  if (ev && typeof ev.clientX === "number" && (ev.clientX || ev.clientY)) return [ev.clientX, ev.clientY];
  const r = el.getBoundingClientRect();
  return [r.left + Math.min(40, r.width / 2), r.top + r.height / 2];
}

// ------------------------------------------------------------------ Kategorie-Auswahl (9.1)
/** ``optionen.konten``: auch Bestandskonten anbieten (D-242: die Zuordnung wird zur Umbuchung), ohne
 *  ``optionen.ohneKonto`` (das Konto des Blatts). */
export function kategorieAuswahl(titel, ausloeser, optionen) {
  const o = optionen || {};
  let angelegt = null;   // läuft das Anlegen einer neuen Kategorie (D-264), wartet das Ergebnis darauf
  const d = dialog("kategorie-auswahl", titel || "Kategorie wählen", (inhalt, dd) => {
    const listeId = neueId("kat-liste");
    const suche = h("input", { type: "text", tid: "kategorie-auswahl-suche", role: "combobox",
      "aria-label": "Kategorien filtern", "aria-controls": listeId, "aria-expanded": "true", autocomplete: "off",
      "aria-autocomplete": "list" });
    const liste = h("div", { role: "listbox", id: listeId, tid: "kategorie-auswahl-liste", class: "auswahl-liste",
      "aria-label": "Kategorien" });
    const alle = kategorien().map(({ konto }) => {
      const pfad = kontoPfad(konto);
      const el = h("div", { role: "option", id: neueId("kat-opt"), tid: `kategorie-option-${konto.id}`,
        class: "option", "aria-selected": "false" }, pfad);
      el.addEventListener("click", () => dd.schliessen(konto.id));
      return { el, pfad, id: konto.id };
    });
    let kontenKopf = null;
    if (o.konten) {
      const konten = baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art) && !k.geschlossen && k.id !== o.ohneKonto));
      if (konten.length) {
        kontenKopf = h("div", { class: "auswahl-gruppe", role: "presentation", tid: "kategorie-auswahl-konten" },
          "Umbuchung auf ein Konto");
        alle.push({ el: kontenKopf, kopf: true });
      }
      for (const { konto } of konten) {
        const pfad = kontoPfad(konto);
        const el = h("div", { role: "option", id: neueId("kat-opt"), tid: `kategorie-option-${konto.id}`,
          class: "option option-konto", "aria-selected": "false", "data-umbuchung": "ja" }, `→ ${pfad}`);
        el.addEventListener("click", () => dd.schliessen(konto.id));
        alle.push({ el, pfad, id: konto.id, konto: true });
      }
    }
    const wahlbar = () => alle.filter((x) => !x.kopf);
    let markiert = -1;
    const sichtbar = () => wahlbar().filter((x) => !x.el.hidden);
    function markieren(i) {
      const s = sichtbar();
      wahlbar().forEach((x) => x.el.setAttribute("aria-selected", "false"));
      markiert = s.length ? Math.max(0, Math.min(i, s.length - 1)) : -1;
      if (markiert >= 0) {
        s[markiert].el.setAttribute("aria-selected", "true");
        suche.setAttribute("aria-activedescendant", s[markiert].el.id);
        s[markiert].el.scrollIntoView({ block: "nearest" });
      } else suche.removeAttribute("aria-activedescendant");
    }
    function filtern() {
      for (const x of wahlbar()) x.el.hidden = !passt(suche.value, x.pfad);
      if (kontenKopf) kontenKopf.hidden = !wahlbar().some((x) => x.konto && !x.el.hidden);
      markiert = -1;
      wahlbar().forEach((x) => x.el.setAttribute("aria-selected", "false"));
      suche.removeAttribute("aria-activedescendant");
    }
    suche.addEventListener("input", filtern);
    suche.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); markieren(markiert + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); markieren(markiert - 1); }
      else if (e.key === "Enter") {
        e.preventDefault();
        const s = sichtbar();
        const wahl = markiert >= 0 ? s[markiert] : (s.length === 1 ? s[0] : null);
        if (wahl) dd.schliessen(wahl.id);
        else if (!s.length && suche.value.trim()) neuOeffnen();   // nichts gefunden: gleich anlegen (D-264)
      }
    });
    anhaengen(liste, alle.map((x) => x.el));
    // D-264: neue Kategorie aus der Auswahl heraus anlegen; sie ist danach gewählt
    const neuName = h("input", { type: "text", tid: "kategorie-neu-name", maxlength: "200" });
    const neuArt = h("select", { tid: "kategorie-neu-art" },
      ["aufwand", "ertrag"].map((a) => h("option", { value: a }, ART_NAMEN[a])));
    const neuEltern = h("select", { tid: "kategorie-neu-eltern" });
    const elternFuellen = () => {
      neuEltern.replaceChildren(h("option", { value: "" }, "(keine – oberste Ebene)"),
        ...kategorien().filter(({ konto }) => konto.art === neuArt.value)
          .map(({ konto }) => h("option", { value: String(konto.id) }, kontoPfad(konto))));
    };
    neuArt.addEventListener("change", elternFuellen);
    const anlegen = knopf("Anlegen und wählen", { tid: "kategorie-neu-anlegen", class: "knopf knopf-haupt" });
    anlegen.addEventListener("click", () => imDialog(dd, anlegen, async () => {
      const name = neuName.value.trim();
      if (!name) { dd.fehler("Bitte einen Namen eingeben."); return; }
      const body = { name, art: neuArt.value };
      if (neuEltern.value) body.eltern_id = Number(neuEltern.value);
      // Der Dialog schließt vor dem Neuladen; der Aufrufer bekommt die Wahl erst, wenn die Stammdaten da sind.
      angelegt = aktion(() => api("POST", "/api/konten", body), { stillBeiFehler: true,
        danach: (k) => dd.schliessen(k.id), erfolg: `Kategorie „${name}“ angelegt.` });
      await angelegt;
    }));
    neuName.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); anlegen.click(); } });
    const neuForm = h("div", { class: "kategorie-neu", tid: "kategorie-neu", hidden: true },
      feld("Name", neuName), feld("Art", neuArt), feld("Übergeordnete Kategorie", neuEltern),
      knopfLeiste(anlegen, knopf("Zurück zur Auswahl", { tid: "kategorie-neu-zurueck", onclick: () => {
        neuForm.hidden = true; neuKnopf.hidden = false; liste.hidden = false; suche.hidden = false; suche.focus();
      } })));
    function neuOeffnen() {
      neuName.value = suche.value.trim();
      elternFuellen();
      neuForm.hidden = false; neuKnopf.hidden = true; liste.hidden = true; suche.hidden = true;
      neuName.focus();
    }
    const neuKnopf = knopf("Neue Kategorie anlegen…", { tid: "kategorie-auswahl-neu", onclick: neuOeffnen });
    inhalt.append(suche, liste, neuKnopf, neuForm);
  }, { ausloeser, klasse: "dialog-auswahl" });
  return d.ergebnis.then(async (wahl) => {
    try { await angelegt; } catch (e) { /* im Dialog gemeldet */ }
    return wahl;
  });
}

// ------------------------------------------------------------------ Tag-Auswahl (9.2)
/** Führt das Hinzufügen/Entfernen für `ids` selbst aus (in `aktion`, ein Rückgängig-Eintrag). `tagsVon(id)` liefert,
 *  soweit bekannt, die Tags einer Buchung; damit zeigt der Dialog die vorhandenen Tags zum Entfernen (D-216). */
export function tagAuswahl(ids, ausloeser, tagsVon) {
  dialog("tag-auswahl", ids.length === 1 ? "Tags der Buchung" : `Tags für ${ids.length} Buchungen`, (inhalt, d) => {
    // Vorhandene Tags der Auswahl: je Tag ein Chip mit ×; bei mehreren Buchungen mit der Zahl der Buchungen.
    const vorhanden = h("div", { class: "tag-auswahl-vorhanden", tid: "tag-auswahl-vorhanden", role: "list",
      "aria-label": "Vorhandene Tags", "data-geladen": "nein" });
    const stand = new Map();   // Buchung → [{id, name}]
    const zeichnen = () => {
      const zahl = new Map();
      for (const tags of stand.values()) for (const t of tags) zahl.set(t.id, { name: t.name, n: (zahl.get(t.id) || { n: 0 }).n + 1 });
      const chips = [...zahl.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name, "de")).map(([id, t]) =>
        h("span", { class: "tag regel-tag", role: "listitem", "data-tag": String(id) }, t.name,
          ids.length > 1 ? h("small", null, t.n === ids.length ? " (alle)" : ` (${t.n} von ${ids.length})`) : null,
          h("button", { type: "button", class: "regel-tag-weg", tid: `tag-auswahl-weg-${id}`,
            "aria-label": ids.length > 1 ? `Tag ${t.name} von allen gewählten Buchungen entfernen` : `Tag ${t.name} entfernen`,
            onclick: (e) => entfernen(id, t.name, e.currentTarget) }, "×")));
      const unbekannt = ids.length - stand.size;
      vorhanden.replaceChildren(...(chips.length ? chips : [h("span", { class: "klein" }, unbekannt ? "" : "Noch keine Tags.")]),
        unbekannt ? h("span", { class: "klein" }, ` Tags von ${unbekannt} weiteren Buchung(en) werden hier nicht gezeigt.`) : "");
      vorhanden.dataset.geladen = "ja";
    };
    const entfernen = (id, tagname, knopfEl) => imDialog(d, knopfEl, async () => {
      // Der Dialog bleibt offen, damit sich mehrere Tags nacheinander entfernen lassen.
      await aktion(() => api("POST", "/api/buchungen/mehrfach/tags", { buchung_ids: ids, hinzufuegen: [], entfernen: [id] }),
        { stillBeiFehler: true, erfolg: `Tag „${tagname}“ entfernt.` });
      for (const [b, tags] of stand) stand.set(b, tags.filter((t) => t.id !== id));
      zeichnen();
      if (d.offen) name.focus();
    });
    (async () => {
      const fehlend = [];
      for (const id of ids) {
        const tags = tagsVon ? tagsVon(id) : null;
        if (tags) stand.set(id, tags.map((t) => ({ id: t.id, name: t.name }))); else fehlend.push(id);
      }
      for (const id of fehlend.slice(0, 50)) {   // nicht geladene Buchungen einzeln nachlesen (begrenzt)
        try { stand.set(id, (await api("GET", `/api/buchungen/${id}`)).tags.map((t) => ({ id: t.id, name: t.name }))); } catch (e) { /* bleibt unbekannt */ }
      }
      if (d.offen) zeichnen();
    })();
    const listeId = neueId("tags");
    const name = h("input", { type: "text", tid: "tag-auswahl-name", list: listeId, autocomplete: "off",
      maxlength: "200" });
    const vorschlaege = h("datalist", { id: listeId }, stamm.tags.map((t) => h("option", { value: t.name })));
    const finden = (n) => stamm.tags.find((t) => t.name.toLocaleLowerCase("de") === n.toLocaleLowerCase("de")
      || casefold(t.name) === casefold(n));
    const hinzu = knopf("Hinzufügen", { tid: "tag-auswahl-hinzufuegen", class: "knopf knopf-haupt" });
    const weg = knopf("Entfernen", { tid: "tag-auswahl-entfernen" });
    hinzu.addEventListener("click", () => imDialog(d, hinzu, async () => {
      const n = name.value.trim();
      if (!n) { d.fehler("Bitte einen Tag-Namen eingeben."); return; }
      let fehler = null;
      try {
        await aktion(async () => {
          let t = finden(n);
          if (!t) t = await api("POST", "/api/tags", { name: n });
          return api("POST", "/api/buchungen/mehrfach/tags", { buchung_ids: ids, hinzufuegen: [t.id], entfernen: [] });
        }, { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: `Tag „${n}“ hinzugefügt.` });
      } catch (e) { fehler = e; }
      if (fehler) throw fehler;
      d.schliessen(true);
    }));
    weg.addEventListener("click", () => imDialog(d, weg, async () => {
      const n = name.value.trim();
      const t = n ? finden(n) : null;
      if (!t) { d.fehler(n ? `Den Tag „${n}“ gibt es nicht.` : "Bitte einen Tag-Namen eingeben."); return; }
      await aktion(() => api("POST", "/api/buchungen/mehrfach/tags",
        { buchung_ids: ids, hinzufuegen: [], entfernen: [t.id] }), { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: `Tag „${t.name}“ entfernt.` });
    }));
    name.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); hinzu.click(); } });
    inhalt.append(h("div", { class: "feld" }, h("span", { class: "feld-titel" }, ids.length === 1 ? "Vorhandene Tags" : "Vorhandene Tags der Auswahl"), vorhanden),
      feld("Tag hinzufügen oder entfernen", name, "vorhandenen Tag wählen oder neuen Namen eingeben; Enter fügt hinzu"), vorschlaege,
      knopfLeiste(hinzu, weg, knopf("Schließen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

export function casefold(t) {
  return String(t).toLocaleLowerCase("de").replace(/ß/g, "ss").replace(/ς/g, "σ");
}

// ------------------------------------------------------------------ Split-Dialog (9.3)
export function splitDialog(buchung, ausloeser) {
  dialog("split-dialog", "Buchung splitten", (inhalt, d) => {
    const zeilen = buchung.splits.map((s) => ({ konto_id: s.konto_id, betrag: betragEingabe(s.betrag), memo: s.memo }));
    const tabelle = h("div", { class: "split-tabelle" });
    const rest = h("output", { tid: "split-rest", class: "betrag", "data-betrag": "0" });
    const speichern = knopf("Speichern", { tid: "split-speichern", class: "knopf knopf-haupt" });
    const kontoOptionen = baumFolge(stamm.konten).map(({ konto }) => ({ id: konto.id, pfad: kontoPfad(konto) }));
    function pruefen() {
      let summe = 0;
      let gueltig = zeilen.length >= 2;
      zeilen.forEach((z, i) => {
        const c = betragLesen(z.betrag);
        const eing = tid(`split-betrag-${i}`, tabelle);
        if (eing) eing.setAttribute("aria-invalid", c === null || c === "" ? "true" : "false");
        if (c === null || c === "" || !z.konto_id) gueltig = false;
        if (typeof c === "number") summe += c;
      });
      rest.dataset.betrag = String(summe);
      rest.textContent = "Summe: " + betragText(summe);
      speichern.disabled = !(gueltig && summe === 0);
    }
    function zeichnen() {
      tabelle.replaceChildren(...zeilen.map((z, i) => {
        const konto = h("select", { tid: `split-konto-${i}`, "aria-label": `Konto von Split ${i + 1}` },
          h("option", { value: "" }, "– Konto wählen –"),
          kontoOptionen.map((k) => h("option", { value: String(k.id), selected: k.id === z.konto_id }, k.pfad)));
        if (z.konto_id) konto.value = String(z.konto_id);
        konto.addEventListener("change", () => { z.konto_id = konto.value ? Number(konto.value) : null; pruefen(); });
        const betrag = h("input", { type: "text", inputmode: "decimal", tid: `split-betrag-${i}`, value: z.betrag,
          "aria-label": `Betrag von Split ${i + 1} in Euro` });
        betrag.addEventListener("input", () => { z.betrag = betrag.value; pruefen(); });
        const memo = h("input", { type: "text", tid: `split-memo-${i}`, value: z.memo, maxlength: "1000",
          "aria-label": `Memo von Split ${i + 1}` });
        memo.addEventListener("input", () => { z.memo = memo.value; });
        const ausgleichen = knopf("Split Ausgleichen", { tid: `split-ausgleichen-${i}`,
          "aria-label": `Split ${i + 1} ausgleichen`,
          onclick: () => {
            let andere = 0;
            zeilen.forEach((andereZeile, j) => {
              if (j === i) return;
              const c = betragLesen(andereZeile.betrag);
              if (typeof c === "number") andere += c;
            });
            z.betrag = betragEingabe(-andere);
            betrag.value = z.betrag;
            pruefen();
          } });
        const entfernen = knopf("Entfernen", { tid: `split-entfernen-${i}`, "aria-label": `Split ${i + 1} entfernen`,
          onclick: () => { zeilen.splice(i, 1); zeichnen(); } });
        return h("div", { class: "split-zeile", tid: `split-zeile-${i}` }, konto, betrag, memo,
          h("div", { class: "split-aktionen" }, ausgleichen, entfernen));
      }));
      pruefen();
    }
    const hinzufuegen = knopf("Split hinzufügen", { tid: "split-hinzufuegen",
      onclick: () => { zeilen.push({ konto_id: null, betrag: "", memo: "" }); zeichnen(); } });
    const nameVorschlag = String((buchung.empfaenger && buchung.empfaenger.name) || buchung.verwendungszweck || "Split").trim().slice(0, 200);
    const vorlageName = h("input", { type: "text", tid: "split-vorlage-name", maxlength: "200", value: nameVorschlag,
      "aria-label": "Name der Vorlage" });
    const vorlageKnopf = knopf("Diesen Split zur Vorlage machen", { tid: "split-vorlage",
      "aria-label": "Diesen Split zur Vorlage machen" });
    function vorlageKoerper() {
      const name = vorlageName.value.trim();
      if (!name) { d.fehler("Bitte einen Namen für die Vorlage eingeben."); return null; }
      const empfaenger = buchung.empfaenger && buchung.empfaenger.name ? String(buchung.empfaenger.name).trim() : "";
      if (!empfaenger) { d.fehler("Die Buchung hat keinen Empfänger. Eine Split-Vorlage gilt über den Empfänger."); return null; }
      const teile = [];
      for (const z of zeilen) {
        const k = z.konto_id ? kontoNach(z.konto_id) : null;
        if (!k || BESTAND.has(k.art)) continue;
        if (k.art !== "aufwand" && k.art !== "ertrag") {
          d.fehler("Eine Split-Vorlage nimmt nur Kategorien (Ausgaben oder Einnahmen).");
          return null;
        }
        const c = betragLesen(z.betrag);
        if (typeof c !== "number" || c === 0) {
          d.fehler("Jeder Kategorie-Teil braucht einen Betrag ungleich 0.");
          return null;
        }
        teile.push({ kategorie_id: k.id, betrag: c, memo: z.memo || "" });
      }
      if (teile.length < 2) {
        d.fehler("Eine Split-Vorlage braucht mindestens zwei Kategorien. Das Bestandskonto zählt nicht mit.");
        return null;
      }
      if (teile.reduce((s, t) => s + t.betrag, 0) === 0) {
        d.fehler("Die Summe der Kategorie-Teile darf nicht 0 sein.");
        return null;
      }
      return { name, bedingungen: [{ feld: "empfaenger", operator: "gleich", wert: empfaenger.slice(0, 200) }], teile };
    }
    vorlageKnopf.addEventListener("click", () => imDialog(d, vorlageKnopf, async () => {
      const body = vorlageKoerper();
      if (!body) return;
      await aktion(() => api("POST", "/api/vorlagen", body),
        { stillBeiFehler: true, ohneNeuLaden: true, erfolg: "Split-Vorlage angelegt." });
    }));
    speichern.addEventListener("click", () => imDialog(d, speichern, async () => {
      const splits = zeilen.map((z) => ({ konto_id: z.konto_id, betrag: betragLesen(z.betrag), memo: z.memo }));
      // D-272: Splits von Hand bestätigen die Buchung, also auch das Tag der Person – außer es bleibt ein Teil
      // auf „Unkategorisiert“
      const unk = stamm.konten.find((k) => k.extern_id === "kontor:unkategorisiert");
      const offen = (buchung.status === "importiert" || buchung.status === "vorlaeufig")
        && !(unk && splits.some((sp) => sp.konto_id === unk.id)) ? [buchung.id] : [];
      await aktion(async () => {
        const r = await api("PUT", `/api/buchungen/${buchung.id}/splits`, { splits });
        await personBestaetigt(offen);
        return r;
      },
        { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Splits gespeichert." });
    }));
    // D-267: eine Split-Vorlage von Hand übernehmen – auch wenn ihr Betrag nicht zur Buchung passt
    const vorlageWahl = h("select", { tid: "split-vorlage-wahl", "aria-label": "Split-Vorlage übernehmen", disabled: true },
      h("option", { value: "" }, "– Vorlage übernehmen –"));
    const vorlageHinweis = h("p", { class: "hinweis", tid: "split-vorlage-hinweis", hidden: true });
    let vorlagen = [];
    api("GET", "/api/vorlagen").then((liste) => {
      vorlagen = liste;
      for (const v of liste) {
        vorlageWahl.append(h("option", { value: String(v.id) }, `${v.name} (${betragText(Math.abs(v.gesamtbetrag))})`));
      }
      vorlageWahl.disabled = !liste.length;
      if (!liste.length) vorlageWahl.firstChild.textContent = "– keine Split-Vorlagen vorhanden –";
    }).catch(() => { /* Auswahl bleibt gesperrt */ });
    vorlageWahl.addEventListener("change", () => {
      const v = vorlagen.find((x) => String(x.id) === vorlageWahl.value);
      vorlageWahl.value = "";
      if (!v) return;
      // die Seite der Bestandskonten bleibt, die Teile der Vorlage ersetzen die übrigen Zeilen
      const bleibt = zeilen.filter((z) => { const k = z.konto_id ? kontoNach(z.konto_id) : null; return k && BESTAND.has(k.art); });
      zeilen.length = 0;
      zeilen.push(...bleibt, ...v.teile.map((t) => ({ konto_id: t.kategorie_id, betrag: betragEingabe(t.betrag), memo: t.memo || "" })));
      zeichnen();
      const summe = Number(rest.dataset.betrag);
      vorlageHinweis.hidden = summe === 0;
      vorlageHinweis.textContent = summe === 0 ? "" : `Die Vorlage „${v.name}“ lautet auf ${betragText(Math.abs(v.gesamtbetrag))} und passt `
        + `nicht zum Betrag der Buchung. Es bleiben ${betragText(Math.abs(summe))} offen: einen Teil anpassen oder bei einem Teil `
        + "„Split Ausgleichen“ wählen.";
    });
    zeichnen();
    inhalt.append(h("p", null, `${datumText(buchung.datum)} · ${buchung.empfaenger ? buchung.empfaenger.name : ""} · `,
      betragEl("span", buchung.betrag)), feld("Split-Vorlage", vorlageWahl), vorlageHinweis, tabelle, hinzufuegen, rest,
    h("div", { class: "split-vorlage" }, feld("Name der Vorlage", vorlageName), vorlageKnopf),
    knopfLeiste(speichern, knopf("Abbrechen", { tid: "split-abbrechen", onclick: () => d.schliessen(null) })));
  }, { ausloeser, klasse: "dialog-breit" });
}

// ------------------------------------------------------------------ Ziel-Auswahl (9.4)
export function zielAuswahl(konto, ausloeser) {
  const nachfahren = new Set([konto.id]);
  let geaendert = true;
  while (geaendert) {
    geaendert = false;
    for (const k of stamm.konten) {
      if (k.eltern_id && nachfahren.has(k.eltern_id) && !nachfahren.has(k.id)) { nachfahren.add(k.id); geaendert = true; }
    }
  }
  const ziele = baumFolge(stamm.konten.filter((k) => klasse(k) === klasse(konto) && !nachfahren.has(k.id)));
  const d = dialog("ziel-auswahl", `„${konto.name}“ verschieben nach …`, (inhalt, dd) => {
    const liste = h("div", { role: "listbox", class: "auswahl-liste", "aria-label": "Ziel", tabindex: "0" });
    const optionen = [{ id: null, text: "Oberste Ebene", testid: "ziel-option-wurzel", ebene: 1 }]
      .concat(ziele.map(({ konto: k }) => ({ id: k.id, text: kontoPfad(k), testid: `ziel-option-${k.id}` })));
    let markiert = 0;
    const els = optionen.map((o, i) => {
      const el = h("div", { role: "option", tid: o.testid, id: neueId("ziel"), class: "option",
        "aria-selected": i === 0 ? "true" : "false" }, o.text);
      el.addEventListener("click", () => dd.schliessen({ eltern_id: o.id }));
      return el;
    });
    function markieren(i) {
      markiert = Math.max(0, Math.min(i, els.length - 1));
      els.forEach((e, j) => e.setAttribute("aria-selected", j === markiert ? "true" : "false"));
      liste.setAttribute("aria-activedescendant", els[markiert].id);
      els[markiert].scrollIntoView({ block: "nearest" });
    }
    liste.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); markieren(markiert + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); markieren(markiert - 1); }
      else if (e.key === "Enter") { e.preventDefault(); dd.schliessen({ eltern_id: optionen[markiert].id }); }
    });
    anhaengen(liste, els);
    inhalt.append(liste, knopfLeiste(knopf("Abbrechen", { onclick: () => dd.schliessen(null) })));
  }, { ausloeser, fokus: (b) => b.querySelector('[role="listbox"]') });
  return d.ergebnis;
}

// ------------------------------------------------------------------ Konto-Dialog (8.2, 13.1, 13.3)
/** vorgabe: {art, eltern_id, arten: [...], titel, iban: bool} */
export function kontoDialog(vorgabe, ausloeser) {
  const v = vorgabe || {};
  dialog("konto-dialog", v.titel || "Konto anlegen", (inhalt, d) => {
    const name = h("input", { type: "text", tid: "konto-name", maxlength: "200", required: true });
    inhalt.append(feld("Name", name));
    let art = null;
    if (v.arten) {
      art = h("select", { tid: "konto-art" }, v.arten.map((a) => h("option", { value: a }, ART_NAMEN[a] || a)));
      inhalt.append(feld("Art", art));
    }
    let iban = null;
    if (v.iban) {
      iban = h("input", { type: "text", tid: "konto-iban", maxlength: "42", autocomplete: "off", spellcheck: "false" });
      inhalt.append(feld("IBAN (optional)", iban));
    }
    const speichern = knopf("Speichern", { tid: "konto-speichern", class: "knopf knopf-haupt" });
    speichern.addEventListener("click", () => imDialog(d, speichern, async () => {
      if (!name.value.trim()) { d.fehler("Bitte einen Namen eingeben."); return; }
      const body = { name: name.value.trim(), art: art ? art.value : v.art };
      if (v.eltern_id) body.eltern_id = v.eltern_id;
      if (iban && iban.value.trim()) body.iban = iban.value.trim();
      await aktion(() => api("POST", "/api/konten", body), { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: `„${body.name}“ angelegt.` });
    }));
    name.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); speichern.click(); } });
    inhalt.append(knopfLeiste(speichern, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

const ART_NAMEN = { girokonto: "Girokonto", sparkonto: "Sparkonto", kreditkonto: "Kreditkonto",
  aufwand: "Ausgaben (Aufwand)", ertrag: "Einnahmen (Ertrag)" };

// ------------------------------------------------------------------ Konto löschen (9.7, loeschen.md 5)
export async function kontoLoeschen(konto, ausloeser) {
  const pfad = `/api/konten/${konto.id}/loeschen`;
  let probe;
  try {
    probe = await api("POST", pfad, { buchungen: "unkategorisiert", konflikte: "behalten", trocken: true });
  } catch (e) { melde("fehler", e.message); return; }
  const leer = !probe.buchungen_betroffen.length && !probe.unterkonten.length && !probe.regeln_geaendert.length
    && !probe.regeln_geloescht.length;
  if (leer) {
    if (!(await bestaetigen(`Konto „${konto.name}“ löschen?`, { ja: "Löschen", ausloeser }))) return;
    try {
      await aktion(() => api("DELETE", `/api/konten/${konto.id}`), { erfolg: `„${konto.name}“ gelöscht.` });
    } catch (e) { /* gemeldet */ }
    return;
  }
  dialog("loeschen-dialog", `Konto „${konto.name}“ löschen`, (inhalt, d) => {
    const regeln = new Set([...probe.regeln_geaendert, ...probe.regeln_geloescht]);
    const zahl = (t, n, text) => h("li", null, h("strong", { tid: t, "data-anzahl": String(n) }, String(n)), " " + text);
    inhalt.append(h("ul", { class: "loeschen-zahlen" },
      zahl("loeschen-anzahl-buchungen", probe.buchungen_betroffen.length, "Buchungen betroffen"),
      zahl("loeschen-anzahl-unterkonten", probe.unterkonten.length, "Unterkonten"),
      zahl("loeschen-anzahl-regeln", regeln.size, "Regeln betroffen")));
    const name = neueId("loeschen-wahl");
    const wahl = (wert, text, gesperrt) => {
      const i = h("input", { type: "radio", name, value: wert, tid: `loeschen-wahl-${wert}`, disabled: gesperrt });
      i.addEventListener("change", probelauf);
      return h("label", { class: "wahl" + (gesperrt ? " gesperrt" : "") }, i, " " + text);
    };
    inhalt.append(h("fieldset", null, h("legend", null, "Was geschieht mit den Buchungen?"),
      wahl("loeschen", "Buchungen löschen"),
      wahl("elternkonto", "dem Elternkonto zuordnen", !konto.eltern_id),
      wahl("unkategorisiert", "„Unkategorisiert“ zuordnen")));
    const konflikte = h("div", { tid: "loeschen-konflikte", hidden: true });
    const gesperrt = h("label", { class: "wahl", hidden: true }, h("input", { type: "checkbox",
      tid: "loeschen-gesperrte-bestaetigen" }), " Auch abgestimmte/abgeglichene Buchungen einbeziehen");
    gesperrt.querySelector("input").addEventListener("change", pruefen);
    const ausfuehren = knopf("Löschen", { tid: "loeschen-ausfuehren", class: "knopf knopf-gefahr", disabled: true });
    inhalt.append(konflikte, gesperrt, knopfLeiste(ausfuehren,
      knopf("Abbrechen", { tid: "loeschen-abbrechen", onclick: () => d.schliessen(null) })));
    let letzte = null;
    const gewaehlt = () => (inhalt.querySelector(`input[name="${name}"]:checked`) || {}).value;
    const konfliktWahl = () => (konflikte.querySelector("input[type=radio]:checked") || {}).value;
    async function probelauf() {
      const v = gewaehlt();
      letzte = null;
      pruefen();
      await imDialog(d, null, async () => {
        letzte = await api("POST", pfad, { buchungen: v, konflikte: "behalten", trocken: true });
      });
      if (!letzte || gewaehlt() !== v) return;
      konflikte.hidden = !letzte.konfliktbuchungen.length;
      konflikte.replaceChildren();
      if (letzte.konfliktbuchungen.length) {
        const kn = neueId("konflikte");
        konflikte.append(h("p", null, "Diese Buchungen hätten danach keinen Gegensplit mehr:"),
          h("ul", null, letzte.konfliktbuchungen.map((id) => h("li", { tid: `loeschen-konflikt-${id}` }, `Buchung ${id}`))),
          h("label", { class: "wahl" }, h("input", { type: "radio", name: kn, value: "loeschen",
            tid: "loeschen-konflikte-loeschen", onchange: pruefen }), " Konfliktbuchungen löschen"),
          h("label", { class: "wahl" }, h("input", { type: "radio", name: kn, value: "behalten",
            tid: "loeschen-konflikte-behalten", onchange: pruefen }), " Konfliktbuchungen behalten"));
      }
      gesperrt.hidden = !letzte.gesperrt.length;
      pruefen();
    }
    function pruefen() {
      const ok = letzte && gewaehlt() && (!letzte.konfliktbuchungen.length || konfliktWahl())
        && (!letzte.gesperrt.length || gesperrt.querySelector("input").checked);
      ausfuehren.disabled = !ok;
    }
    ausfuehren.addEventListener("click", () => imDialog(d, ausfuehren, async () => {
      const body = { buchungen: gewaehlt(), konflikte: letzte.konfliktbuchungen.length ? konfliktWahl() : "behalten" };
      if (letzte.gesperrt.length) body.gesperrte_einbeziehen = true;
      await aktion(() => api("POST", pfad, body), { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: `„${konto.name}“ gelöscht.` });
    }));
  }, { ausloeser, fokus: (b) => b.querySelector("input:not([disabled])") });
}

// ------------------------------------------------------------------ Kategorien zusammenführen (D-126)
/** Dialog `zusammenfuehren-dialog`: Buchungen der markierten Kategorien auf eine Zielkategorie umbuchen. */
export function kategorienZusammenfuehren(quellen, ausloeser) {
  const ids = new Set(quellen.map((k) => k.id));
  const ziele = baumFolge(stamm.konten.filter((k) => (k.art === "aufwand" || k.art === "ertrag") && !ids.has(k.id)));
  const titel = quellen.length === 1 ? `„${quellen[0].name}“ zusammenführen` : `${quellen.length} Kategorien zusammenführen`;
  dialog("zusammenfuehren-dialog", titel, (inhalt, d) => {
    inhalt.append(h("p", null, "Quellen: ", h("span", { tid: "zusammenfuehren-quellen" },
      quellen.map((k) => kontoPfad(k)).join(", "))));
    const suche = h("input", { type: "search", tid: "zusammenfuehren-suche", placeholder: "Zielkategorie suchen …",
      "aria-label": "Zielkategorie suchen" });
    const liste = h("div", { role: "listbox", class: "auswahl-liste", tid: "zusammenfuehren-ziele",
      "aria-label": "Zielkategorie", tabindex: "0" });
    let ziel = null;
    const kontoVon = new Map();
    const els = ziele.map(({ konto: k }) => {
      const el = h("div", { role: "option", tid: `zusammenfuehren-ziel-${k.id}`, id: neueId("zz"), class: "option",
        "aria-selected": "false", "data-text": kontoPfad(k).toLowerCase() },
      kontoPfad(k), k.art === "ertrag" ? " (Einnahme)" : "");
      el.addEventListener("click", () => waehlen(k, el));
      kontoVon.set(el, k);
      return el;
    });
    anhaengen(liste, els);
    suche.addEventListener("input", () => {
      const t = suche.value.trim().toLowerCase();
      for (const el of els) el.hidden = !!t && !el.dataset.text.includes(t);
    });
    const loeschen = h("input", { type: "checkbox", tid: "zusammenfuehren-loeschen", checked: true });
    const gesperrt = h("label", { class: "wahl", hidden: true }, h("input", { type: "checkbox",
      tid: "zusammenfuehren-gesperrte-bestaetigen" }), " Auch abgestimmte/abgeglichene Buchungen einbeziehen");
    const info = h("p", { tid: "zusammenfuehren-vorschau", "aria-live": "polite", class: "klein" });
    const ausfuehren = knopf("Zusammenführen", { tid: "zusammenfuehren-ausfuehren", class: "knopf knopf-haupt", disabled: true });
    inhalt.append(suche, liste, h("label", { class: "wahl" }, loeschen, " Quellkategorien danach löschen"
      + " (Unterkategorien und Regeln gehen an das Ziel)"), info, gesperrt,
    knopfLeiste(ausfuehren, knopf("Abbrechen", { tid: "zusammenfuehren-abbrechen", onclick: () => d.schliessen(null) })));
    let probe = null;
    const koerper = () => ({ quelle_ids: [...ids], ziel_id: ziel.id, quellen_loeschen: loeschen.checked });
    async function vorschau() {
      probe = null;
      pruefen();
      if (!ziel) return;
      await imDialog(d, null, async () => { probe = await api("POST", "/api/kategorien/zusammenfuehren",
        { ...koerper(), trocken: true }); });
      if (!probe) return;
      info.textContent = `${probe.buchungen_umgebucht.length} Buchungen werden auf „${kontoPfad(ziel)}“ umgebucht`
        + (probe.unterkategorien_verschoben.length ? `, ${probe.unterkategorien_verschoben.length} Unterkategorien wandern mit` : "")
        + (probe.regeln_geaendert.length ? `, ${probe.regeln_geaendert.length} Regeln werden umgestellt` : "") + ".";
      info.dataset.anzahl = String(probe.buchungen_umgebucht.length);
      gesperrt.hidden = !probe.gesperrt.length;
      pruefen();
    }
    function waehlen(k, el) {
      ziel = k;
      els.forEach((e) => e.setAttribute("aria-selected", e === el ? "true" : "false"));
      liste.setAttribute("aria-activedescendant", el.id);
      vorschau();
    }
    loeschen.addEventListener("change", vorschau);
    gesperrt.querySelector("input").addEventListener("change", pruefen);
    function pruefen() {
      ausfuehren.disabled = !(ziel && probe && (!probe.gesperrt.length || gesperrt.querySelector("input").checked));
    }
    liste.addEventListener("keydown", (e) => {
      const sichtbar = els.filter((x) => !x.hidden);
      const i = sichtbar.findIndex((x) => x.getAttribute("aria-selected") === "true");
      const neu = e.key === "ArrowDown" ? sichtbar[Math.min(i + 1, sichtbar.length - 1)]
        : e.key === "ArrowUp" ? sichtbar[Math.max(i - 1, 0)] : null;
      if (neu) { e.preventDefault(); neu.scrollIntoView({ block: "nearest" }); waehlen(kontoVon.get(neu), neu); }
    });
    ausfuehren.addEventListener("click", () => imDialog(d, ausfuehren, async () => {
      const body = koerper();
      if (probe.gesperrt.length) body.gesperrte_einbeziehen = true;
      await aktion(() => api("POST", "/api/kategorien/zusammenfuehren", body), { stillBeiFehler: true,
        danach: () => d.schliessen(true), erfolg: `Zusammengeführt in „${ziel.name}“.` });
    }));
  }, { ausloeser, fokus: (b) => b.querySelector('[data-testid="zusammenfuehren-suche"]') });
}

// ------------------------------------------------------------------ Dubletten-Dialog (9.6)
function dubletteText(verdacht) {
  if (verdacht.grund === "gleich") return "Gleicher Betrag, gleiches Buchungsdatum und gleicher Empfänger.";
  if (verdacht.grund === "manuell") return "Diese beiden Buchungen als Dublette prüfen.";
  if (verdacht.grund === "mehrdeutig") return "Mehrere mögliche Gegenstücke gefunden.";
  return "Ähnliche Buchung gefunden.";
}

/** Reihenfolge fürs Anlegen: die erste Id wird beim Zusammenführen entfernt, behalten_id ist Kandidat. */
export function dubletteIds(verdacht, body) {
  const alle = [verdacht.buchung_id, ...verdacht.kandidat_ids];
  if (body.entscheidung !== "zusammenfuehren") return alle;
  const weg = alle.filter((id) => id !== body.behalten_id);
  if (!weg.length) return alle;
  return [weg[0], body.behalten_id, ...weg.slice(1)];
}

/** Bestehenden Verdacht auflösen. Ohne Id erst anlegen (Vorschlag oder manuelles Paar); Abbrechen ruft das nicht auf. */
export async function dubletteAufloesen(verdacht, body) {
  let id = verdacht.id;
  if (id == null) {
    const neu = await api("POST", "/api/dubletten", { buchung_ids: dubletteIds(verdacht, body) });
    id = neu.id;
  }
  return api("POST", `/api/dubletten/${id}/aufloesen`, body);
}

export async function dubletteDialog(verdacht, ausloeser) {
  const ids = [verdacht.buchung_id, ...verdacht.kandidat_ids];
  let buchungen;
  try { buchungen = await Promise.all(ids.map((id) => api("GET", `/api/buchungen/${id}`))); }
  catch (e) { melde("fehler", e.message); return; }
  const frei = verdacht.id == null;
  dialog("dublette-dialog", frei ? "Als Dublette markieren" : "Dublettenverdacht", (inhalt, d) => {
    const zeile = (b, mitKnopf) => h("li", { tid: mitKnopf ? `dublette-kandidat-${b.id}` : null, class: "dublette" },
      `${datumText(b.datum)} · ${b.empfaenger ? b.empfaenger.name : "ohne Empfänger"} · ${b.verwendungszweck || ""} · `,
      betragEl("span", b.betrag),
      mitKnopf ? knopf("Diese behalten", { tid: `dublette-zusammenfuehren-${b.id}`,
        "aria-label": `Buchung ${b.id} behalten und zusammenführen`,
        onclick: (e) => aufloesen(e.currentTarget, { entscheidung: "zusammenfuehren", behalten_id: b.id }) }) : null);
    async function aufloesen(k, body) {
      await imDialog(d, k, async () => {
        await aktion(() => dubletteAufloesen(verdacht, body),
          { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Dublettenverdacht aufgelöst." });
      });
    }
    inhalt.append(h("p", { tid: "dublette-erklaerung" }, dubletteText(verdacht)),
    h("ul", { class: "dubletten" }, buchungen.map((b, i) => zeile(b, frei || i > 0))),
    knopfLeiste(knopf("Keine Dublette", { tid: "dublette-keine",
      onclick: (e) => aufloesen(e.currentTarget, { entscheidung: "keine_dublette" }) }),
    knopf("Abbrechen", { tid: "dublette-abbrechen", onclick: () => d.schliessen(null) })));
  }, { ausloeser, klasse: "dialog-breit" });
}

// ------------------------------------------------------------------ Buchung erfassen (9.8)
export function erfassenDialog(kontoId, ausloeser) {
  dialog("erfassen-dialog", "Buchung erfassen", (inhalt, d) => {
    const art = h("select", { tid: "erfassen-art" }, [["ausgabe", "Ausgabe"], ["einnahme", "Einnahme"],
      ["umbuchung", "Umbuchung"], ["korrektur", "Korrektur"]].map(([w, t]) => h("option", { value: w }, t)));
    const datum = h("input", { type: "date", tid: "erfassen-datum", required: true });
    const betrag = h("input", { type: "text", inputmode: "decimal", tid: "erfassen-betrag", required: true });
    const empf = h("input", { type: "text", tid: "erfassen-empfaenger", maxlength: "200", list: "erfassen-empf-liste" });
    const empfListe = h("datalist", { id: "erfassen-empf-liste" }, stamm.empfaenger.map((e) => h("option", { value: e.name })));
    const zweck = h("input", { type: "text", tid: "erfassen-verwendungszweck", maxlength: "10000" });
    const kat = h("select", { tid: "erfassen-kategorie" }, h("option", { value: "" }, "– Kategorie wählen –"),
      kategorien().map(({ konto }) => h("option", { value: String(konto.id) }, kontoPfad(konto))));
    const gegen = h("select", { tid: "erfassen-gegenkonto" }, h("option", { value: "" }, "– Gegenkonto wählen –"),
      baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art) && k.id !== kontoId && !k.geschlossen))
        .map(({ konto }) => h("option", { value: String(konto.id) }, kontoPfad(konto))));
    const katFeld = feld("Kategorie", kat);
    const gegenFeld = feld("Gegenkonto", gegen);
    const sichtbarkeit = () => {
      katFeld.hidden = !(art.value === "ausgabe" || art.value === "einnahme");
      gegenFeld.hidden = art.value !== "umbuchung";
    };
    art.addEventListener("change", sichtbarkeit);
    sichtbarkeit();
    const speichern = knopf("Speichern", { tid: "erfassen-speichern", class: "knopf knopf-haupt" });
    speichern.addEventListener("click", () => imDialog(d, speichern, async () => {
      const c = betragLesen(betrag.value);
      betrag.setAttribute("aria-invalid", typeof c === "number" && c > 0 ? "false" : "true");
      if (typeof c !== "number" || c <= 0) { d.fehler("Bitte einen positiven Betrag eingeben (z. B. 12,34)."); return; }
      const body = { art: art.value, datum: datum.value, konto_id: kontoId, betrag: c, verwendungszweck: zweck.value };
      if (empf.value.trim()) body.empfaenger_name = empf.value.trim();
      if ((art.value === "ausgabe" || art.value === "einnahme") && kat.value) body.kategorie_id = Number(kat.value);
      if (art.value === "umbuchung" && gegen.value) body.gegenkonto_id = Number(gegen.value);
      await aktion(() => api("POST", "/api/buchungen/erfassen", body), { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Buchung erfasst." });
    }));
    inhalt.append(feld("Art", art), feld("Datum", datum), feld("Betrag (€)", betrag), feld("Empfänger", empf), empfListe,
      feld("Verwendungszweck", zweck), katFeld, gegenFeld,
      knopfLeiste(speichern, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

// ------------------------------------------------------------------ Kontenabstimmung (13.3)
export function abstimmungDialog(konto, ausloeser) {
  dialog("abstimmung-dialog", `Abstimmung „${konto.name}“`, (inhalt, d) => {
    const stichtag = h("input", { type: "date", tid: "abstimmung-stichtag", required: true });
    const saldo = h("input", { type: "text", inputmode: "decimal", tid: "abstimmung-saldo", required: true });
    const ergebnis = h("div", { class: "abstimmung-ergebnis", "aria-live": "polite" });
    const pruefenK = knopf("Prüfen", { tid: "abstimmung-pruefen" });
    const speichern = knopf("Abstimmen", { tid: "abstimmung-speichern", class: "knopf knopf-haupt" });
    const koerper = (trocken) => {
      const c = betragLesen(saldo.value);
      saldo.setAttribute("aria-invalid", typeof c === "number" ? "false" : "true");
      if (typeof c !== "number" || !stichtag.value) throw new ApiFehler(422, { meldung: "Bitte Stichtag und Saldo angeben." });
      return { konto_id: konto.id, stichtag: stichtag.value, saldo: c, trocken };
    };
    pruefenK.addEventListener("click", () => imDialog(d, pruefenK, async () => {
      const r = await api("POST", "/api/abstimmungen", koerper(true));
      ergebnis.replaceChildren(h("p", null, "Berechneter Saldo: ", betragEl("span", r.berechneter_saldo),
        " · Differenz: ", betragEl("span", r.differenz), r.stimmt ? " · stimmt" : " · stimmt nicht"));
    }));
    speichern.addEventListener("click", () => imDialog(d, speichern, async () => {
      const body = koerper(false);
      const r = await aktion(() => api("POST", "/api/abstimmungen", body), { stillBeiFehler: true,
        danach: (e) => { if (e && e.abgestimmt) d.schliessen(true); } });
      if (r && r.abgestimmt) melde("erfolg", "Konto abgestimmt.", { rueckgaengig: true });
      else if (r) d.fehler(`Der Saldo stimmt nicht (Differenz ${betragText(r.differenz)}).`);
    }));
    inhalt.append(feld("Stichtag", stichtag), feld("Saldo laut Kontoauszug (€)", saldo), ergebnis,
      knopfLeiste(pruefenK, speichern, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

export { kontoNach };

// ------------------------------------------------------------------ Kontoeinstellungen (D-111)
/** Bekannte Bankkonten: Zustand je Bankkonto und nicht zugeordnete aus dem letzten Lauf. */
export async function bankkontenBekannt() {
  const [zustand, laeufe] = await Promise.all([api("GET", "/api/sync/konten").catch(() => []),
    api("GET", "/api/sync/laeufe").catch(() => [])]);
  const m = new Map();
  for (const z of zustand) m.set(z.iban, { iban: z.iban, name: null });
  const letzter = laeufe.slice().sort((a, b) => b.id - a.id)[0];
  for (const u of (letzter && letzter.uebersprungen) || []) m.set(u.iban, { iban: u.iban, name: u.name });
  for (const l of laeufe) for (const k of l.konten || []) if (!m.has(k.iban)) m.set(k.iban, { iban: k.iban, name: null });
  return [...m.values()].sort((a, b) => a.iban.localeCompare(b.iban));
}

export async function kontoEinstellungen(konto, ausloeser) {
  const bestand = BESTAND.has(konto.art);
  const bekannt = bestand ? await bankkontenBekannt() : [];
  dialog("konto-einstellungen", `Einstellungen „${konto.name}“`, (inhalt, d) => {
    const name = h("input", { type: "text", tid: "einstellungen-name", maxlength: "200", value: konto.name });
    inhalt.append(feld("Name", name));
    let sync = null;
    let ibanFrei = null;
    if (bestand) {
      const belegt = new Map(stamm.konten.filter((k) => k.iban && k.id !== konto.id).map((k) => [k.iban, k]));
      sync = h("select", { tid: "einstellungen-sync" }, h("option", { value: "" }, "– keins (keine Synchronisation) –"),
        bekannt.map((b) => {
          const anderes = belegt.get(b.iban);
          return h("option", { value: b.iban, disabled: !!anderes },
            `${b.name ? `${b.name} · ` : ""}${b.iban}${anderes ? ` (gehört zu „${anderes.name}“)` : ""}`);
        }),
        h("option", { value: "*" }, "Andere IBAN eingeben…"));
      ibanFrei = h("input", { type: "text", tid: "einstellungen-iban", maxlength: "42", autocomplete: "off",
        spellcheck: "false", hidden: true, placeholder: "IBAN" });
      if (konto.iban && !bekannt.some((b) => b.iban === konto.iban)) {
        sync.prepend(h("option", { value: konto.iban }, konto.iban));
      }
      sync.value = konto.iban || "";
      sync.addEventListener("change", () => { ibanFrei.hidden = sync.value !== "*"; if (!ibanFrei.hidden) ibanFrei.focus(); });
      inhalt.append(feld("Synchronisationskonto", h("div", null, sync, ibanFrei),
        "Bankkonto, dessen Umsätze bei der Synchronisation in dieses Konto übernommen werden."));
    }
    const eroeffnet = h("input", { type: "date", tid: "einstellungen-eroeffnet", value: konto.eroeffnet_am || "" });
    const geschlossen = h("input", { type: "checkbox", tid: "einstellungen-geschlossen" });
    geschlossen.checked = !!konto.geschlossen;
    const notiz = h("textarea", { tid: "einstellungen-notiz", rows: "3", maxlength: "10000" });
    notiz.value = konto.notiz || "";
    inhalt.append(feld("Eröffnet am", eroeffnet),
      h("label", { class: "auswahl-zeile" }, geschlossen, " Konto ist geschlossen"), feld("Notiz", notiz));
    const speichern = knopf("Speichern", { tid: "einstellungen-speichern", class: "knopf knopf-haupt" });
    speichern.addEventListener("click", () => imDialog(d, speichern, async () => {
      const body = {};
      const n = name.value.trim();
      if (!n) { d.fehler("Bitte einen Namen eingeben."); return; }
      if (n !== konto.name) body.name = n;
      if (sync) {
        const iban = sync.value === "*" ? ibanFrei.value.replace(/\s+/g, "").toUpperCase() : sync.value;
        if (sync.value === "*" && !iban) { d.fehler("Bitte eine IBAN eingeben."); return; }
        if ((iban || null) !== (konto.iban || null)) body.iban = iban || null;
      }
      if ((eroeffnet.value || null) !== (konto.eroeffnet_am || null)) body.eroeffnet_am = eroeffnet.value || null;
      if (geschlossen.checked !== !!konto.geschlossen) body.geschlossen = geschlossen.checked;
      if (notiz.value !== (konto.notiz || "")) body.notiz = notiz.value;
      if (!Object.keys(body).length) { d.schliessen(null); return; }
      await aktion(() => api("PATCH", `/api/konten/${konto.id}`, body), { stillBeiFehler: true,
        danach: () => d.schliessen(true), erfolg: "Einstellungen gespeichert." });
    }));
    inhalt.append(knopfLeiste(speichern, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

// ------------------------------------------------------------------ Bankkonto zuordnen (D-111)
/**
 * Fragt für ein bei der Synchronisation übersprungenes Bankkonto `{iban, name, art}`, welches Konto seine Umsätze
 * aufnimmt: ein vorhandenes Bestandskonto ohne Synchronisationskonto oder ein neues. Trägt die IBAN in den
 * Kontoeinstellungen ein. Ergebnis: true (zugeordnet), false (übersprungen), null (abgebrochen).
 */
export async function zuordnungDialog(bk, ausloeser, hinweis) {
  // frischer Stand vom Server: die vorige Zuordnung einer Reihe kann noch nicht in `stamm` angekommen sein
  let konten = stamm.konten;
  try { konten = await api("GET", "/api/konten"); } catch (e) { /* Stand der Oberfläche */ }
  const frei = baumFolge(konten.filter((k) => BESTAND.has(k.art) && !k.iban)).map((x) => x.konto);
  const d = dialog("zuordnung-dialog", "Bankkonto zuordnen", (inhalt, dd) => {
    const name = neueId("zuordnung-wahl");
    const radio = (wert, text, attrs) => h("label", { class: "auswahl-zeile" },
      h("input", { type: "radio", name, value: wert, tid: `zuordnung-${wert}`, ...(attrs || {}) }), " ", text);
    const vorhanden = h("select", { tid: "zuordnung-konto" }, frei.map((k) => h("option", { value: String(k.id) }, kontoPfad(k))));
    const neuName = h("input", { type: "text", tid: "zuordnung-name", maxlength: "200", value: bk.name || bk.iban });
    const neuArt = h("select", { tid: "zuordnung-art" }, ["girokonto", "sparkonto", "kreditkonto"].map((a) =>
      h("option", { value: a }, ART_NAMEN[a])));
    neuArt.value = BESTAND.has(bk.art) ? bk.art : "girokonto";
    // gleichnamiges freies Konto vorschlagen, sonst ein neues Konto
    const gleich = frei.find((k) => k.name.trim().toLocaleLowerCase("de") === (bk.name || "").trim().toLocaleLowerCase("de"));
    if (gleich) vorhanden.value = String(gleich.id);
    const rVorhanden = radio("vorhanden", "Vorhandenes Konto verwenden:", { disabled: !frei.length, checked: !!gleich });
    const rNeu = radio("neu", "Neues Konto anlegen:", { checked: !gleich });
    const wahl = () => (inhalt.querySelector(`input[name='${name}']:checked`) || {}).value;
    const aktualisieren = () => {
      vorhanden.disabled = wahl() !== "vorhanden";
      neuName.disabled = neuArt.disabled = wahl() !== "neu";
    };
    inhalt.addEventListener("change", aktualisieren);
    const ok = knopf("Zuordnen", { tid: "zuordnung-ok", class: "knopf knopf-haupt" });
    ok.addEventListener("click", () => imDialog(dd, ok, async () => {
      if (wahl() === "vorhanden") {
        const k = frei.find((x) => x.id === Number(vorhanden.value));
        await aktion(() => api("PATCH", `/api/konten/${k.id}`, { iban: bk.iban }), { stillBeiFehler: true,
          danach: () => dd.schliessen(true), erfolg: `Bankkonto „${bk.name || bk.iban}“ → „${k.name}“ zugeordnet.` });
      } else {
        const n = neuName.value.trim();
        if (!n) { dd.fehler("Bitte einen Namen eingeben."); return; }
        await aktion(() => api("POST", "/api/konten", { name: n, art: neuArt.value, iban: bk.iban }), { stillBeiFehler: true,
          danach: () => dd.schliessen(true), erfolg: `Konto „${n}“ für das Bankkonto angelegt.` });
      }
    }));
    inhalt.append(...[h("p", null, "Für das Bankkonto ", h("strong", null, bk.name || bk.iban), ` (IBAN ${bk.iban}) gibt es noch kein Konto. `
      + "Wohin sollen seine Umsätze übernommen werden?"), hinweis ? h("p", { class: "hinweis" }, hinweis) : null,
    h("fieldset", { class: "umfang" }, h("legend", null, "Konto"), rVorhanden, vorhanden, rNeu,
      h("div", { class: "formular-zeile" }, feld("Name", neuName), feld("Art", neuArt))),
    h("p", { class: "hinweis" }, "Die IBAN wird in den Einstellungen des Kontos als Synchronisationskonto eingetragen."),
    knopfLeiste(ok, knopf("Später", { tid: "zuordnung-spaeter", onclick: () => dd.schliessen(false) }))].filter(Boolean));
    aktualisieren();
  }, { ausloeser });
  return d.ergebnis;
}
