/* Kontor – Single-Page-Weboberfläche (Vanilla-JS, ohne externe Abhängigkeiten).
 * Nutzt ausschließlich die REST-API aus openapi.yaml. Beträge sind ganze Cent;
 * Umrechnung in Euro-Text geschieht nur mit Ganzzahlarithmetik.
 */
(function () {
  "use strict";

  // ------------------------------------------------------------ Hilfen
  const $ = (sel, wurzel) => (wurzel || document).querySelector(sel);

  function h(tag, attrs, ...kinder) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") el.className = v;
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else if (k === "value") el.value = v;
        else if (k === "checked") el.checked = !!v;
        else el.setAttribute(k, v === true ? "" : String(v));
      }
    }
    for (const kind of kinder.flat(Infinity)) {
      if (kind === null || kind === undefined || kind === false) continue;
      el.append(kind instanceof Node ? kind : document.createTextNode(String(kind)));
    }
    return el;
  }

  function betragText(cent, mitWaehrung = true) {
    if (cent === null || cent === undefined) return "";
    const neg = cent < 0;
    const abs = Math.abs(cent);
    const euro = Math.trunc(abs / 100);
    const rest = abs % 100;
    const tausender = String(euro).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return (neg ? "−" : "") + tausender + "," + String(rest).padStart(2, "0") + (mitWaehrung ? " €" : "");
  }

  /** "1.234,56" / "-12,5" / "12" → Cent (Ganzzahl) oder null. */
  function betragLesen(text) {
    if (text === null || text === undefined) return null;
    let t = String(text).trim().replace(/\s|€/g, "").replace(/−/g, "-");
    if (t === "") return null;
    let neg = false;
    if (t.startsWith("-")) { neg = true; t = t.slice(1); } else if (t.startsWith("+")) { t = t.slice(1); }
    if (/^\d{1,3}(\.\d{3})+(,\d{0,2})?$/.test(t)) t = t.replace(/\./g, "");
    else if (/^\d+\.\d{1,2}$/.test(t)) t = t.replace(".", ",");
    const m = /^(\d+)(?:,(\d{0,2}))?$/.exec(t);
    if (!m) return null;
    const cent = Number(m[1]) * 100 + Number((m[2] || "").padEnd(2, "0"));
    if (!Number.isSafeInteger(cent)) return null;
    return neg ? -cent : cent;
  }

  function betragZelle(cent) {
    return h("td", { class: "zahl " + (cent < 0 ? "negativ" : cent > 0 ? "positiv" : "") }, betragText(cent));
  }

  function datumText(iso) {
    if (!iso) return "";
    const [j, m, t] = iso.split("-");
    return `${t}.${m}.${j}`;
  }

  const STATUS_TEXT = { importiert: "importiert", vorlaeufig: "vorläufig", bestaetigt: "bestätigt", abgeglichen: "abgeglichen" };
  const ART_TEXT = { girokonto: "Girokonto", sparkonto: "Sparkonto", kreditkonto: "Kreditkonto",
    aufwand: "Aufwand", ertrag: "Ertrag", eigenkapital: "Eigenkapital" };
  const BESTAND = new Set(["girokonto", "sparkonto", "kreditkonto"]);

  function melden(text, fehler = false) {
    const el = h("div", { class: "meldung" + (fehler ? " fehler" : ""), role: fehler ? "alert" : "status" }, text);
    $("#meldungen").append(el);
    setTimeout(() => el.remove(), fehler ? 8000 : 4000);
  }

  class ApiFehler extends Error {
    constructor(status, fehler) {
      super(fehler && fehler.meldung ? fehler.meldung : "Fehler " + status);
      this.status = status;
      this.code = fehler ? fehler.code : "unbekannt";
      this.details = fehler ? fehler.details : null;
    }
  }

  async function api(methode, pfad, koerper, roh) {
    const opt = { method: methode, headers: {} };
    if (roh) opt.body = roh;
    else if (koerper !== undefined) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(koerper);
    }
    const r = await fetch(pfad, opt);
    if (r.status === 204) return null;
    let daten = null;
    try { daten = await r.json(); } catch (e) { daten = null; }
    if (!r.ok) throw new ApiFehler(r.status, daten && daten.fehler);
    return daten;
  }

  function query(params) {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === null || v === undefined || v === "" || v === false) continue;
      if (Array.isArray(v)) v.forEach((x) => u.append(k, x));
      else u.append(k, v === true ? "true" : v);
    }
    const s = u.toString();
    return s ? "?" + s : "";
  }

  // ------------------------------------------------------------ Stammdaten
  const stamm = { konten: [], tags: [], empfaenger: [], status: null };

  async function stammLaden() {
    const [konten, tags, empfaenger] = await Promise.all([
      api("GET", "/api/konten"), api("GET", "/api/tags"), api("GET", "/api/empfaenger")]);
    stamm.konten = konten; stamm.tags = tags; stamm.empfaenger = empfaenger;
  }

  const kontoNach = (id) => stamm.konten.find((k) => k.id === id);

  function kontoPfad(k) {
    const teile = [];
    let x = k;
    const gesehen = new Set();
    while (x && !gesehen.has(x.id)) { gesehen.add(x.id); teile.unshift(x.name); x = x.eltern_id ? kontoNach(x.eltern_id) : null; }
    return teile.join(" › ");
  }

  /** Konten als Baum (Tiefensuche), jeweils mit Tiefe. */
  function baum(konten) {
    const ids = new Set(konten.map((k) => k.id));
    const kinder = new Map();
    for (const k of konten) {
      const e = k.eltern_id && ids.has(k.eltern_id) ? k.eltern_id : 0;
      if (!kinder.has(e)) kinder.set(e, []);
      kinder.get(e).push(k);
    }
    const aus = [];
    const besuche = (e, tiefe) => {
      for (const k of (kinder.get(e) || []).sort((a, b) => a.name.localeCompare(b.name, "de"))) {
        aus.push({ konto: k, tiefe });
        besuche(k.id, tiefe + 1);
      }
    };
    besuche(0, 0);
    return aus;
  }

  function kategorieOptionen(ausgewaehlt, mitLeer) {
    const kats = stamm.konten.filter((k) => k.ist_kategorie);
    const opts = mitLeer ? [h("option", { value: "" }, mitLeer)] : [];
    for (const { konto, tiefe } of baum(kats)) {
      opts.push(h("option", { value: konto.id, selected: konto.id === ausgewaehlt },
        "  ".repeat(tiefe) + konto.name + " (" + ART_TEXT[konto.art] + ")"));
    }
    return opts;
  }

  function kontoOptionen(ausgewaehlt, filter) {
    const liste = stamm.konten.filter(filter || (() => true));
    return baum(liste).map(({ konto, tiefe }) => h("option", { value: konto.id, selected: konto.id === ausgewaehlt },
      "  ".repeat(tiefe) + konto.name + " – " + ART_TEXT[konto.art]));
  }

  // ------------------------------------------------------------ Layout
  const rahmen = $(".rahmen");
  const LAYOUT = "kontor.layout";

  function layoutLaden() {
    try {
      const l = JSON.parse(localStorage.getItem(LAYOUT) || "{}");
      if (l.breite) document.documentElement.style.setProperty("--nav-breite", l.breite + "px");
      rahmen.classList.toggle("nav-zu", !!l.zu);
    } catch (e) { /* ignorieren */ }
  }

  function layoutSpeichern(aenderung) {
    let l = {};
    try { l = JSON.parse(localStorage.getItem(LAYOUT) || "{}"); } catch (e) { l = {}; }
    localStorage.setItem(LAYOUT, JSON.stringify(Object.assign(l, aenderung)));
  }

  function trennerEinrichten() {
    const t = $("#trenner");
    t.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      t.setPointerCapture(ev.pointerId);
      rahmen.classList.remove("nav-zu");
      const bewegen = (e) => {
        const b = Math.max(160, Math.min(480, e.clientX));
        document.documentElement.style.setProperty("--nav-breite", b + "px");
      };
      const ende = (e) => {
        t.removeEventListener("pointermove", bewegen);
        t.removeEventListener("pointerup", ende);
        layoutSpeichern({ breite: Math.max(160, Math.min(480, e.clientX)), zu: false });
      };
      t.addEventListener("pointermove", bewegen);
      t.addEventListener("pointerup", ende);
    });
    t.addEventListener("dblclick", () => {
      const zu = !rahmen.classList.contains("nav-zu");
      rahmen.classList.toggle("nav-zu", zu);
      layoutSpeichern({ zu });
    });
  }

  function navUmschalten(offen) {
    const auf = offen === undefined ? !document.body.classList.contains("nav-offen") : offen;
    document.body.classList.toggle("nav-offen", auf);
    $("#menue-knopf").setAttribute("aria-expanded", auf ? "true" : "false");
  }

  // ------------------------------------------------------------ Kontextmenü
  const menue = $("#kontextmenue");

  function menueZeigen(x, y, eintraege) {
    menue.replaceChildren();
    for (const e of eintraege) {
      if (e === "-") { menue.append(h("hr")); continue; }
      menue.append(h("button", { type: "button", role: "menuitem", disabled: e.aus, onclick: () => { menueSchliessen(); e.tun(); } }, e.text));
    }
    menue.hidden = false;
    const b = menue.getBoundingClientRect();
    menue.style.left = Math.max(4, Math.min(x, window.innerWidth - b.width - 4)) + "px";
    menue.style.top = Math.max(4, Math.min(y, window.innerHeight - b.height - 4)) + "px";
    const erster = menue.querySelector("button:not([disabled])");
    if (erster) erster.focus();
  }

  function menueSchliessen() { menue.hidden = true; }

  document.addEventListener("pointerdown", (e) => { if (!menue.hidden && !menue.contains(e.target)) menueSchliessen(); });
  window.addEventListener("blur", menueSchliessen);
  window.addEventListener("resize", menueSchliessen);

  /** Rechtsklick und lange Berührung (Smartphone) auf einem Element. */
  function kontextAuf(el, oeffnen) {
    el.addEventListener("contextmenu", (e) => { e.preventDefault(); oeffnen(e.clientX, e.clientY, e); });
    let timer = null, start = null;
    el.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) return;
      const t = e.touches[0];
      start = { x: t.clientX, y: t.clientY };
      timer = setTimeout(() => { timer = null; el.dataset.langGedrueckt = "1"; oeffnen(start.x, start.y, e); }, 550);
    }, { passive: true });
    const abbrechen = () => { if (timer) { clearTimeout(timer); timer = null; } };
    el.addEventListener("touchmove", (e) => {
      const t = e.touches[0];
      if (start && (Math.abs(t.clientX - start.x) > 10 || Math.abs(t.clientY - start.y) > 10)) abbrechen();
    }, { passive: true });
    el.addEventListener("touchend", (e) => {
      abbrechen();
      if (el.dataset.langGedrueckt) { e.preventDefault(); setTimeout(() => delete el.dataset.langGedrueckt, 50); }
    });
    el.addEventListener("touchcancel", abbrechen);
  }

  // ------------------------------------------------------------ Dialoge
  const huelle = $("#dialog-huelle");

  function dialog(titel, inhalt, knoepfe) {
    return new Promise((fertig) => {
      const schliessen = (wert) => { huelle.hidden = true; huelle.replaceChildren(); document.removeEventListener("keydown", taste); fertig(wert); };
      const taste = (e) => { if (e.key === "Escape") schliessen(null); };
      document.addEventListener("keydown", taste);
      const form = h("form", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-label": titel },
        h("h2", null, titel), inhalt,
        h("div", { class: "knoepfe" }, h("button", { type: "button", class: "knopf", onclick: () => schliessen(null) }, "Abbrechen"),
          (knoepfe || []).map((k) => h("button", { type: k.submit ? "submit" : "button", class: "knopf " + (k.klasse || ""),
            onclick: k.submit ? null : async () => { const w = await k.tun(); if (w !== undefined) schliessen(w); } }, k.text))));
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const k = (knoepfe || []).find((x) => x.submit);
        if (!k) return;
        try { const w = await k.tun(); if (w !== undefined) schliessen(w); } catch (err) { melden(err.message, true); }
      });
      huelle.replaceChildren(form);
      huelle.hidden = false;
      const f = form.querySelector("input, select, textarea");
      if (f) f.focus();
    });
  }

  async function bestaetigen(text) {
    return (await dialog("Bitte bestätigen", h("p", null, text), [{ text: "OK", klasse: "primaer", submit: true, tun: () => true }])) === true;
  }

  async function kategorieDialog(ids) {
    const sel = h("select", { required: true }, kategorieOptionen(null, "– Kategorie wählen –"));
    const w = await dialog(`Kategorie für ${ids.length} Buchung${ids.length === 1 ? "" : "en"} setzen`,
      h("label", { class: "feld" }, "Kategorie", sel),
      [{ text: "Setzen", klasse: "primaer", submit: true, tun: () => (sel.value ? Number(sel.value) : undefined) }]);
    if (!w) return false;
    try {
      await api("POST", "/api/buchungen/mehrfach/kategorie", { buchung_ids: ids, kategorie_id: w });
      melden(`Kategorie für ${ids.length} Buchung(en) gesetzt.`);
      return true;
    } catch (e) {
      const betroffen = e.details && e.details.buchung_ids ? ` (Buchungen: ${e.details.buchung_ids.join(", ")})` : "";
      melden(e.message + betroffen + " – es wurde nichts geändert.", true);
      return false;
    }
  }

  async function tagsDialog(ids, buchungen) {
    await stammLaden();
    const zaehler = new Map();
    for (const b of buchungen) for (const t of b.tags) zaehler.set(t.id, (zaehler.get(t.id) || 0) + 1);
    const zeilen = stamm.tags.map((t) => {
      const sel = h("select", null, h("option", { value: "" }, "unverändert"), h("option", { value: "+" }, "hinzufügen"),
        h("option", { value: "-" }, "entfernen"));
      sel.dataset.tag = t.id;
      const n = zaehler.get(t.id) || 0;
      return h("label", null, h("span", null, h("span", { class: "tag" }, t.name)), h("span", { class: "leise" }, `${n}/${ids.length}`), sel);
    });
    const neu = h("input", { type: "text", placeholder: "Neuen Tag anlegen und hinzufügen", maxlength: 100 });
    const inhalt = h("div", null, stamm.tags.length ? h("div", { class: "tagliste" }, zeilen) : h("p", { class: "leise" }, "Noch keine Tags."),
      h("label", { class: "feld", style: "margin-top:.8rem" }, "Neuer Tag", neu));
    const w = await dialog(`Tags für ${ids.length} Buchung${ids.length === 1 ? "" : "en"}`, inhalt,
      [{ text: "Übernehmen", klasse: "primaer", submit: true, tun: async () => {
        const hinzu = [], weg = [];
        for (const s of inhalt.querySelectorAll("select")) {
          if (s.value === "+") hinzu.push(Number(s.dataset.tag));
          if (s.value === "-") weg.push(Number(s.dataset.tag));
        }
        if (neu.value.trim()) {
          const t = await api("POST", "/api/tags", { name: neu.value.trim() });
          hinzu.push(t.id);
        }
        return { hinzu, weg };
      } }]);
    if (!w) return false;
    try {
      await api("POST", "/api/buchungen/mehrfach/tags", { buchung_ids: ids, hinzufuegen: w.hinzu, entfernen: w.weg });
      melden("Tags aktualisiert.");
      return true;
    } catch (e) { melden(e.message, true); return false; }
  }

  async function empfaengerId(name) {
    const n = (name || "").trim();
    if (!n) return null;
    const vorhanden = stamm.empfaenger.find((e) => e.name === n);
    if (vorhanden) return vorhanden.id;
    const e = await api("POST", "/api/empfaenger", { name: n });
    stamm.empfaenger.push(e);
    return e.id;
  }

  function empfaengerFeld(wert) {
    const id = "empf-liste-" + Math.random().toString(36).slice(2);
    return [h("input", { type: "text", list: id, value: wert || "", maxlength: 200, placeholder: "ohne Empfänger" }),
      h("datalist", { id }, stamm.empfaenger.map((e) => h("option", { value: e.name })))];
  }

  async function buchungDialog(b) {
    await stammLaden();
    const gesperrt = b.status === "abgeglichen";
    const datum = h("input", { type: "date", value: b.datum, required: true, disabled: gesperrt });
    const [empf, liste] = empfaengerFeld(b.empfaenger ? b.empfaenger.name : "");
    empf.disabled = gesperrt;
    const zweck = h("textarea", { rows: 2, maxlength: 10000, disabled: gesperrt }, b.verwendungszweck);
    const erlaubt = { importiert: ["importiert", "bestaetigt"], vorlaeufig: ["vorlaeufig", "abgeglichen"],
      bestaetigt: ["bestaetigt", "abgeglichen"], abgeglichen: ["abgeglichen"] }[b.status];
    const status = h("select", null, erlaubt.map((s) => h("option", { value: s, selected: s === b.status }, STATUS_TEXT[s])));
    const splitBox = h("div");
    const summe = h("p", { class: "leise" });
    const splitZeile = (s) => {
      const konto = h("select", { disabled: gesperrt }, kontoOptionen(s.konto_id));
      const betrag = h("input", { type: "text", inputmode: "decimal", value: s.betrag === null ? "" : betragText(s.betrag, false), disabled: gesperrt, oninput: neuRechnen });
      const memo = h("input", { type: "text", class: "split-memo", value: s.memo || "", placeholder: "Memo", maxlength: 10000, disabled: gesperrt });
      const weg = h("button", { type: "button", class: "knopf", title: "Split entfernen", disabled: gesperrt, onclick: () => { zeile.remove(); neuRechnen(); } }, "×");
      const zeile = h("div", { class: "split-zeile" }, konto, betrag, memo, weg);
      zeile._lesen = () => ({ konto_id: Number(konto.value), betrag: betragLesen(betrag.value), memo: memo.value });
      return zeile;
    };
    function neuRechnen() {
      const werte = [...splitBox.children].map((z) => z._lesen());
      if (werte.some((w) => w.betrag === null)) { summe.textContent = "Ungültiger Betrag."; return; }
      const s = werte.reduce((a, w) => a + w.betrag, 0);
      summe.textContent = s === 0 ? "Ausgeglichen (Summe 0)." : "Summe der Splits: " + betragText(s) + " – muss 0 sein.";
      summe.className = s === 0 ? "leise" : "negativ";
    }
    b.splits.forEach((s) => splitBox.append(splitZeile(s)));
    neuRechnen();
    const inhalt = h("div", null,
      gesperrt ? h("p", { class: "marke-status" }, "Abgeglichen – nur Tags sind änderbar.") : null,
      h("label", { class: "feld" }, "Datum", datum),
      h("label", { class: "feld" }, "Empfänger", empf, liste),
      h("label", { class: "feld" }, "Verwendungszweck", zweck),
      h("label", { class: "feld" }, "Status", status),
      h("h2", null, "Splits"), splitBox,
      gesperrt ? null : h("button", { type: "button", class: "knopf", onclick: () => { splitBox.append(splitZeile({ konto_id: null, betrag: 0, memo: "" })); neuRechnen(); } }, "+ Split"),
      summe,
      b.extern_ids.length ? h("p", { class: "leise" }, "Herkunft: " + b.extern_ids.join(", ")) : null);
    const w = await dialog("Buchung #" + b.id, inhalt, [{ text: "Speichern", klasse: "primaer", submit: true, tun: async () => {
      const aenderung = {};
      if (!gesperrt) {
        if (datum.value !== b.datum) aenderung.datum = datum.value;
        const eid = await empfaengerId(empf.value);
        if (eid !== (b.empfaenger ? b.empfaenger.id : null)) aenderung.empfaenger_id = eid;
        if (zweck.value !== b.verwendungszweck) aenderung.verwendungszweck = zweck.value;
      }
      if (status.value !== b.status) aenderung.status = status.value;
      const splits = [...splitBox.children].map((z) => z._lesen());
      const splitsGeaendert = !gesperrt && JSON.stringify(splits) !== JSON.stringify(b.splits.map((s) => ({ konto_id: s.konto_id, betrag: s.betrag, memo: s.memo })));
      if (splitsGeaendert) {
        if (splits.some((s) => s.betrag === null)) throw new Error("Ein Split hat einen ungültigen Betrag.");
        await api("PUT", `/api/buchungen/${b.id}/splits`, { splits });
      }
      if (Object.keys(aenderung).length) await api("PATCH", `/api/buchungen/${b.id}`, aenderung);
      return true;
    } }]);
    if (w) melden("Buchung gespeichert.");
    return !!w;
  }

  async function neueBuchungDialog(kontoId) {
    await stammLaden();
    const heute = new Date();
    const iso = `${heute.getFullYear()}-${String(heute.getMonth() + 1).padStart(2, "0")}-${String(heute.getDate()).padStart(2, "0")}`;
    const konto = h("select", null, kontoOptionen(kontoId, (k) => BESTAND.has(k.art)));
    const datum = h("input", { type: "date", value: iso, required: true });
    const [empf, liste] = empfaengerFeld("");
    const zweck = h("input", { type: "text", maxlength: 10000 });
    const betrag = h("input", { type: "text", inputmode: "decimal", placeholder: "z. B. -12,34 (Ausgabe) oder 100 (Eingang)", required: true });
    const gegen = h("select", { required: true }, h("option", { value: "" }, "– Kategorie oder Gegenkonto –"), kontoOptionen(null));
    const w = await dialog("Neue Buchung", h("div", null,
      h("label", { class: "feld" }, "Konto", konto), h("label", { class: "feld" }, "Datum", datum),
      h("label", { class: "feld" }, "Betrag (Sicht des Kontos)", betrag), h("label", { class: "feld" }, "Kategorie / Gegenkonto", gegen),
      h("label", { class: "feld" }, "Empfänger", empf, liste), h("label", { class: "feld" }, "Verwendungszweck", zweck)),
    [{ text: "Anlegen", klasse: "primaer", submit: true, tun: async () => {
      const c = betragLesen(betrag.value);
      if (c === null) throw new Error("Ungültiger Betrag.");
      if (!gegen.value) throw new Error("Bitte Kategorie oder Gegenkonto wählen.");
      const body = { datum: datum.value, verwendungszweck: zweck.value,
        splits: [{ konto_id: Number(konto.value), betrag: c }, { konto_id: Number(gegen.value), betrag: -c }] };
      const eid = await empfaengerId(empf.value);
      if (eid) body.empfaenger_id = eid;
      return await api("POST", "/api/buchungen", body);
    } }]);
    if (w) melden("Buchung angelegt.");
    return !!w;
  }

  async function kontoDialog(k, vorgabeArt) {
    await stammLaden();
    const neu = !k;
    const name = h("input", { type: "text", value: k ? k.name : "", required: true, maxlength: 200 });
    const art = h("select", { disabled: !neu }, Object.entries(ART_TEXT).map(([a, t]) => h("option", { value: a, selected: (k ? k.art : vorgabeArt) === a }, t)));
    const eltern = h("select");
    const iban = h("input", { type: "text", value: k && k.iban ? k.iban : "", placeholder: "nur Giro-, Spar-, Kreditkonto" });
    const eroeffnet = h("input", { type: "date", value: k && k.eroeffnet_am ? k.eroeffnet_am : "" });
    const notiz = h("textarea", { rows: 2, maxlength: 10000 }, k ? k.notiz : "");
    const geschlossen = h("input", { type: "checkbox", checked: k ? k.geschlossen : false });
    const klasse = (a) => (BESTAND.has(a) ? "bestand" : a);
    const elternFuellen = () => {
      eltern.replaceChildren(h("option", { value: "" }, "– keines (Wurzelkonto) –"),
        kontoOptionen(k ? k.eltern_id : null, (x) => klasse(x.art) === klasse(art.value) && (!k || x.id !== k.id)));
    };
    art.addEventListener("change", elternFuellen);
    elternFuellen();
    const w = await dialog(neu ? "Konto anlegen" : "Konto bearbeiten", h("div", null,
      h("label", { class: "feld" }, "Name", name), h("label", { class: "feld" }, "Art", art),
      h("label", { class: "feld" }, "Elternkonto", eltern), h("label", { class: "feld" }, "IBAN", iban),
      h("label", { class: "feld" }, "Eröffnet am", eroeffnet), h("label", { class: "feld" }, "Notiz", notiz),
      h("label", null, geschlossen, " geschlossen")),
    [{ text: "Speichern", klasse: "primaer", submit: true, tun: async () => {
      const body = { name: name.value, eltern_id: eltern.value ? Number(eltern.value) : null,
        iban: iban.value.trim() ? iban.value : null, eroeffnet_am: eroeffnet.value || null,
        notiz: notiz.value, geschlossen: geschlossen.checked };
      if (neu) { body.art = art.value; return await api("POST", "/api/konten", body); }
      return await api("PATCH", `/api/konten/${k.id}`, body);
    } }]);
    if (w) melden("Konto gespeichert.");
    return !!w;
  }

  // ------------------------------------------------------------ Buchungsliste
  /**
   * Buchungsliste mit Filtern, Sortierung, Paginierung, Mehrfachauswahl
   * (Strg/Umschalt), Kontextmenü (Rechtsklick/lange Berührung).
   * basis: feste Filter, z. B. {konto_id} oder {kategorie_id, unterkategorien}.
   */
  function buchungsliste(ziel, basis, optionen) {
    const zustand = { filter: optionen && optionen.vorschlag ? { vorschlag: optionen.vorschlag } : {}, sortierung: "-datum", seite: 1, pro_seite: 100, auswahl: new Set(), anker: null, daten: null };
    const kontoSicht = basis.konto_id !== undefined;

    const f = {
      von: h("input", { type: "date" }), bis: h("input", { type: "date" }),
      betrag_min: h("input", { type: "text", inputmode: "decimal", placeholder: "min. €" }),
      betrag_max: h("input", { type: "text", inputmode: "decimal", placeholder: "max. €" }),
      empfaenger: h("select", null, h("option", { value: "" }, "alle"), h("option", { value: "-" }, "ohne Empfänger"),
        stamm.empfaenger.map((e) => h("option", { value: e.id }, e.name))),
      verwendungszweck: h("input", { type: "search", placeholder: "enthält …" }),
      kategorie: h("select", null, kategorieOptionen(null, "alle")),
      unter: h("input", { type: "checkbox", checked: true }),
      tag: h("select", { multiple: true, size: Math.min(4, Math.max(2, stamm.tags.length)) }, stamm.tags.map((t) => h("option", { value: t.id }, t.name))),
      suche: h("input", { type: "search", placeholder: "Empfänger, Zweck, Memo, Tags", id: "freitext" }),
      status: Object.keys(STATUS_TEXT).map((s) => h("input", { type: "checkbox", value: s })),
      vorschlag: h("select", { name: "vorschlag" }, h("option", { value: "" }, "alle"),
        h("option", { value: "true" }, "nur mit Vorschlag"), h("option", { value: "false" }, "ohne Vorschlag")),
    };
    const filterForm = h("form", { class: "filter-form" },
      h("div", { class: "filter" },
        h("label", null, "Freitext", f.suche),
        h("label", null, "Von", f.von), h("label", null, "Bis", f.bis),
        h("label", null, "Betrag ab", f.betrag_min), h("label", null, "Betrag bis", f.betrag_max),
        h("label", null, "Empfänger", f.empfaenger),
        h("label", null, "Verwendungszweck", f.verwendungszweck),
        basis.kategorie_id === undefined ? h("label", null, "Kategorie", f.kategorie) : null,
        basis.kategorie_id === undefined ? h("label", { style: "flex-direction:row;align-items:center;gap:.3rem" }, f.unter, "mit Unterkategorien") : null,
        stamm.tags.length ? h("label", null, "Tags (alle)", f.tag) : null,
        h("label", null, "Kategorie-Vorschlag", f.vorschlag),
        h("div", null, h("div", { class: "leise", style: "font-size:.82rem" }, "Status"),
          h("div", { class: "status-wahl" }, f.status.map((c) => h("label", null, c, STATUS_TEXT[c.value]))))),
      h("div", { class: "filter-zeile" },
        h("button", { type: "submit", class: "knopf primaer" }, "Filtern"),
        h("button", { type: "button", class: "knopf", onclick: () => { filterForm.reset(); f.unter.checked = true; zustand.filter = {}; zustand.seite = 1; laden(); } }, "Zurücksetzen")));
    if (zustand.filter.vorschlag) f.vorschlag.value = zustand.filter.vorschlag;
    filterForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const fl = {};
      if (f.suche.value.trim()) fl.suche = f.suche.value.trim();
      if (f.von.value) fl.von = f.von.value;
      if (f.bis.value) fl.bis = f.bis.value;
      for (const k of ["betrag_min", "betrag_max"]) {
        if (f[k].value.trim()) {
          const c = betragLesen(f[k].value);
          if (c === null) { melden("Ungültiger Betrag im Filter.", true); return; }
          fl[k] = c;
        }
      }
      if (f.empfaenger.value === "-") fl.ohne_empfaenger = true;
      else if (f.empfaenger.value) fl.empfaenger_id = Number(f.empfaenger.value);
      if (f.verwendungszweck.value.trim()) fl.verwendungszweck = f.verwendungszweck.value.trim();
      if (f.kategorie.value && basis.kategorie_id === undefined) { fl.kategorie_id = Number(f.kategorie.value); fl.unterkategorien = f.unter.checked; }
      const tags = [...f.tag.selectedOptions].map((o) => Number(o.value));
      if (tags.length) fl.tag_id = tags;
      const st = f.status.filter((c) => c.checked).map((c) => c.value);
      if (st.length) fl.status = st;
      if (f.vorschlag.value) fl.vorschlag = f.vorschlag.value;
      zustand.filter = fl; zustand.seite = 1;
      laden();
    });

    const werkzeug = h("div", { class: "werkzeug" });
    const tabelle = h("table", { class: "tabelle buchungen" });
    const seiten = h("div", { class: "seiten" });
    const filterKasten = h("details", { class: "karte filter-karte", open: !window.matchMedia("(max-width: 800px)").matches },
      h("summary", null, "Filter"), filterForm);
    ziel.append(filterKasten, werkzeug, tabelle, seiten);

    function werkzeugZeichnen() {
      const n = zustand.auswahl.size;
      werkzeug.replaceChildren(...[
        optionen && optionen.neu ? h("button", { type: "button", class: "knopf", onclick: async () => { if (await neueBuchungDialog(basis.konto_id)) laden(); } }, "+ Neue Buchung") : null,
        h("span", { class: "auswahl-info" }, n ? `${n} markiert` : ""),
        h("button", { type: "button", class: "knopf", disabled: !n, onclick: () => aktion("kategorie") }, "Kategorie setzen"),
        h("button", { type: "button", class: "knopf", disabled: !n, onclick: () => aktion("tags") }, "Tags …"),
        h("button", { type: "button", class: "knopf", disabled: !mitVorschlag().length, title: "Vorschläge der markierten Buchungen annehmen",
          onclick: () => aktion("annehmen") }, "✓ Vorschläge annehmen"),
        h("button", { type: "button", class: "knopf", disabled: !mitVorschlag().length, title: "Vorschläge der markierten Buchungen ablehnen",
          onclick: () => aktion("ablehnen") }, "✗ ablehnen"),
        h("button", { type: "button", class: "knopf", disabled: !n, onclick: () => { zustand.auswahl.clear(); auswahlZeigen(); } }, "Auswahl aufheben"),
        h("span", { class: "leise nur-breit" }, "Strg/Umschalt + Klick: Mehrfachauswahl · Rechtsklick: Menü · Doppelklick: bearbeiten")].filter((x) => x !== null && x !== undefined));
    }

    function eintraegeMarkiert() {
      return (zustand.daten ? zustand.daten.eintraege : []).filter((b) => zustand.auswahl.has(b.id));
    }

    function mitVorschlag() {
      return eintraegeMarkiert().filter((b) => b.vorschlag);
    }

    async function aktion(was, einzel) {
      const ids = einzel ? [einzel.id] : [...zustand.auswahl];
      const liste = einzel ? [einzel] : eintraegeMarkiert();
      if (!ids.length) return;
      let geaendert = false;
      if (was === "annehmen" || was === "ablehnen") {
        const ziel = (einzel ? [einzel] : mitVorschlag()).filter((b) => b.vorschlag).map((b) => b.id);
        if (!ziel.length) { melden("Keine markierte Buchung hat einen offenen Vorschlag.", true); return; }
        try {
          if (ziel.length === 1) await api("POST", `/api/buchungen/${ziel[0]}/vorschlag`, { aktion: was });
          else await api("POST", "/api/buchungen/mehrfach/vorschlag", { buchung_ids: ziel, aktion: was });
          melden(`${ziel.length} Vorschl${ziel.length === 1 ? "ag" : "äge"} ${was === "annehmen" ? "angenommen" : "abgelehnt"}.`);
          geaendert = true;
        } catch (e) { melden(e.message + " – es wurde nichts geändert.", true); }
      } else if (was === "kategorie") geaendert = await kategorieDialog(ids);
      else if (was === "tags") geaendert = await tagsDialog(ids, liste);
      else if (was === "bearbeiten") geaendert = await buchungDialog(await api("GET", `/api/buchungen/${ids[0]}`));
      else if (was === "bestaetigen" || was === "abgleichen") {
        const ziel = was === "bestaetigen" ? "bestaetigt" : "abgeglichen";
        let ok = 0, fehler = 0;
        for (const id of ids) {
          try { await api("PATCH", `/api/buchungen/${id}`, { status: ziel }); ok++; } catch (e) { fehler++; }
        }
        melden(`${ok} Buchung(en) ${STATUS_TEXT[ziel]}` + (fehler ? `, ${fehler} nicht zulässig` : "") + ".", fehler > 0 && ok === 0);
        geaendert = ok > 0;
      } else if (was === "loeschen") {
        if (await bestaetigen(`${ids.length} Buchung(en) wirklich löschen?`)) {
          let fehler = 0;
          for (const id of ids) { try { await api("DELETE", `/api/buchungen/${id}`); } catch (e) { fehler++; } }
          if (fehler) melden(`${fehler} Buchung(en) konnten nicht gelöscht werden (abgeglichen?).`, true);
          zustand.auswahl.clear();
          geaendert = true;
        }
      }
      if (geaendert) { await stammLaden(); laden(); }
    }

    function menueFuer(b, x, y) {
      if (!zustand.auswahl.has(b.id)) { zustand.auswahl = new Set([b.id]); zustand.anker = b.id; auswahlZeigen(); }
      const n = zustand.auswahl.size;
      const plural = n > 1 ? ` (${n})` : "";
      menueZeigen(x, y, [
        { text: "Bearbeiten / splitten …", aus: n !== 1, tun: () => aktion("bearbeiten", n === 1 ? b : null) },
        { text: "Kategorie setzen …" + plural, tun: () => aktion("kategorie") },
        { text: "Tags …" + plural, tun: () => aktion("tags") },
        { text: "Vorschlag annehmen" + plural, aus: !mitVorschlag().length, tun: () => aktion("annehmen") },
        { text: "Vorschlag ablehnen" + plural, aus: !mitVorschlag().length, tun: () => aktion("ablehnen") },
        "-",
        { text: "Bestätigen" + plural, tun: () => aktion("bestaetigen") },
        { text: "Abgleichen" + plural, tun: () => aktion("abgleichen") },
        { text: "Als Dublette markieren (später)", aus: true, tun: () => {} },
        "-",
        { text: "Löschen" + plural, tun: () => aktion("loeschen") },
      ]);
    }

    function auswahlZeigen() {
      for (const tr of tabelle.querySelectorAll("tbody tr[data-id]")) {
        const an = zustand.auswahl.has(Number(tr.dataset.id));
        tr.classList.toggle("markiert", an);
        tr.setAttribute("aria-selected", an ? "true" : "false");
      }
      werkzeugZeichnen();
    }

    function klick(e, b) {
      const ids = zustand.daten.eintraege.map((x) => x.id);
      if (e.shiftKey && zustand.anker !== null && ids.includes(zustand.anker)) {
        const [a, z] = [ids.indexOf(zustand.anker), ids.indexOf(b.id)].sort((p, q) => p - q);
        if (!(e.ctrlKey || e.metaKey)) zustand.auswahl.clear();
        ids.slice(a, z + 1).forEach((id) => zustand.auswahl.add(id));
      } else if (e.ctrlKey || e.metaKey || e.pointerType === "touch" && zustand.auswahl.size > 0) {
        if (zustand.auswahl.has(b.id)) zustand.auswahl.delete(b.id); else zustand.auswahl.add(b.id);
        zustand.anker = b.id;
      } else {
        zustand.auswahl = new Set([b.id]);
        zustand.anker = b.id;
      }
      auswahlZeigen();
    }

    function kopfZelle(text, feld, klasse) {
      const aktiv = zustand.sortierung.replace("-", "") === feld;
      const pfeil = aktiv ? (zustand.sortierung.startsWith("-") ? " ▼" : " ▲") : "";
      return h("th", { class: "sortierbar " + (klasse || ""), "aria-sort": aktiv ? (zustand.sortierung.startsWith("-") ? "descending" : "ascending") : "none",
        onclick: () => { zustand.sortierung = aktiv && !zustand.sortierung.startsWith("-") ? "-" + feld : feld; if (aktiv && zustand.sortierung === feld) zustand.sortierung = feld; laden(); } }, text + pfeil);
    }

    function kategorieText(b) {
      if (b.kategorie_id) { const k = kontoNach(b.kategorie_id); return k ? kontoPfad(k) : "#" + b.kategorie_id; }
      const andere = b.splits.filter((s) => s.konto_id !== basis.konto_id).map((s) => kontoNach(s.konto_id)).filter(Boolean);
      if (b.splits.length > 2) return "Splitbuchung (" + b.splits.length + " Teile)";
      if (andere.length === 1) return (BESTAND.has(andere[0].art) ? "Umbuchung: " : "") + kontoPfad(andere[0]);
      return "–";
    }

    function vorschlagMarke(b) {
      const regel = b.vorschlag.regel_id ? `Regel #${b.vorschlag.regel_id}` : "gelöschte Regel";
      const knopf = (text, was, titel) => h("button", { type: "button", class: "mini-knopf", title: titel, "aria-label": titel,
        onclick: (e) => { e.stopPropagation(); aktion(was, b); }, ondblclick: (e) => e.stopPropagation() }, text);
      return h("span", { class: "vorschlag", title: `Vorschlag (${regel}) – noch nicht bestätigt` }, "Vorschlag",
        knopf("✓", "annehmen", "Vorschlag annehmen"), knopf("✗", "ablehnen", "Vorschlag ablehnen"));
    }

    function zeichnen() {
      const d = zustand.daten;
      const kopf = h("tr", null, kopfZelle("Datum", "datum"), kopfZelle("Empfänger", "empfaenger", "nur-breit"),
        h("th", null, "Kategorie / Zweck"), h("th", { class: "nur-breit" }, "Status"),
        kopfZelle(kontoSicht ? "Betrag" : "Umsatz", "betrag", "zahl"));
      const koerper = h("tbody");
      for (const b of d.eintraege) {
        const tr = h("tr", { "data-id": b.id, tabindex: 0, "aria-selected": "false" },
          h("td", { class: "datum" }, datumText(b.datum)),
          h("td", { class: "nur-breit" }, b.empfaenger ? b.empfaenger.name : h("span", { class: "leise" }, "–")),
          h("td", null, b.empfaenger ? h("div", { class: "nur-schmal" }, h("strong", null, b.empfaenger.name)) : null,
            h("div", { class: b.vorschlag ? "mit-vorschlag" : null }, kategorieText(b), b.vorschlag ? vorschlagMarke(b) : null), b.verwendungszweck ? h("div", { class: "zweck" }, b.verwendungszweck.length > 160 ? b.verwendungszweck.slice(0, 160) + " …" : b.verwendungszweck) : null,
            b.tags.length ? h("div", null, b.tags.map((t) => h("span", { class: "tag" }, t.name))) : null),
          h("td", { class: "nur-breit" }, h("span", { class: "marke-status" }, STATUS_TEXT[b.status])),
          kontoSicht ? betragZelle(b.betrag) : h("td", { class: "zahl" }, betragText(b.betrag)));
        tr.addEventListener("click", (e) => { if (!tr.dataset.langGedrueckt) klick(e, b); });
        tr.addEventListener("dblclick", () => aktion("bearbeiten", b));
        tr.addEventListener("keydown", (e) => {
          if (e.key === "Enter") aktion("bearbeiten", b);
          if (e.key === " ") { e.preventDefault(); klick({ ctrlKey: true }, b); }
          if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) { e.preventDefault(); const r = tr.getBoundingClientRect(); menueFuer(b, r.left + 40, r.bottom); }
        });
        kontextAuf(tr, (x, y) => menueFuer(b, x, y));
        koerper.append(tr);
      }
      const fuss = h("tfoot", null, h("tr", null, h("td", { colspan: 3 }, `${d.gesamt} Buchung${d.gesamt === 1 ? "" : "en"}`),
        h("td", { class: "nur-breit" }), kontoSicht ? betragZelle(d.summe) : h("td", { class: "zahl" }, betragText(d.summe))));
      tabelle.replaceChildren(h("thead", null, kopf), koerper, fuss);
      if (!d.eintraege.length) koerper.append(h("tr", null, h("td", { colspan: 5, class: "leer" }, "Keine Buchungen gefunden.")));
      const maxSeite = Math.max(1, Math.ceil(d.gesamt / zustand.pro_seite));
      seiten.replaceChildren(
        h("button", { type: "button", class: "knopf", disabled: zustand.seite <= 1, onclick: () => { zustand.seite--; laden(); } }, "‹ zurück"),
        h("span", null, `Seite ${zustand.seite} von ${maxSeite}`),
        h("button", { type: "button", class: "knopf", disabled: zustand.seite >= maxSeite, onclick: () => { zustand.seite++; laden(); } }, "weiter ›"));
      auswahlZeigen();
    }

    async function laden() {
      const params = Object.assign({}, basis, zustand.filter, { sortierung: zustand.sortierung, seite: zustand.seite, pro_seite: zustand.pro_seite });
      try {
        zustand.daten = await api("GET", "/api/buchungen" + query(params));
        const sichtbar = new Set(zustand.daten.eintraege.map((b) => b.id));
        zustand.auswahl = new Set([...zustand.auswahl].filter((id) => sichtbar.has(id)));
        zeichnen();
      } catch (e) { melden(e.message, true); }
    }

    ziel._tasten = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a" && zustand.daten && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
        e.preventDefault();
        zustand.auswahl = new Set(zustand.daten.eintraege.map((b) => b.id));
        auswahlZeigen();
      }
      if (e.key === "Escape" && huelle.hidden && menue.hidden) { zustand.auswahl.clear(); auswahlZeigen(); }
      if (e.key === "Delete" && zustand.auswahl.size && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) aktion("loeschen");
    };
    werkzeugZeichnen();
    laden();
  }

  // ------------------------------------------------------------ Ansichten
  const inhalt = $("#inhalt");

  function seite(titel, ...kinder) {
    $("#kopf-titel").textContent = titel;
    document.title = titel + " – Kontor";
    inhalt.replaceChildren(h("h1", null, titel), ...kinder.filter((k) => k !== null && k !== undefined && k !== false));
    inhalt._tasten = null;
  }

  async function ansichtUebersicht() {
    const [u, status] = await Promise.all([api("GET", "/api/kontenuebersicht"), api("GET", "/api/status")]);
    stamm.status = status;
    const bestand = u.konten.filter((k) => BESTAND.has(k.art));
    const tbody = h("tbody");
    const konten = bestand.map((s) => Object.assign({}, kontoNach(s.konto_id) || {}, { id: s.konto_id, name: s.name, art: s.art, eltern_id: s.eltern_id }));
    const sal = new Map(u.konten.map((k) => [k.konto_id, k]));
    for (const { konto, tiefe } of baum(konten)) {
      const s = sal.get(konto.id);
      const tr = h("tr", { class: "klickbar" + (s.geschlossen ? " geschlossen" : ""), onclick: () => { location.hash = "#/konto/" + konto.id; } },
        h("td", null, h("span", { class: "einrueck", style: `width:${tiefe * 1.2}rem` }), konto.name, s.geschlossen ? h("span", { class: "leise" }, " (geschlossen)") : null),
        h("td", { class: "nur-breit" }, ART_TEXT[konto.art]), betragZelle(s.saldo), h("td", { class: "zahl leise nur-breit" }, s.anzahl_buchungen));
      tbody.append(tr);
    }
    const tab = bestand.length ? h("table", { class: "tabelle buchungen" },
      h("thead", null, h("tr", null, h("th", null, "Konto"), h("th", { class: "nur-breit" }, "Art"), h("th", { class: "zahl" }, "Saldo"), h("th", { class: "zahl nur-breit" }, "Buchungen"))),
      tbody, h("tfoot", null, h("tr", null, h("td", null, "Summe Bestandskonten"), h("td", { class: "nur-breit" }), betragZelle(u.summe_bestand), h("td", { class: "nur-breit" }))))
      : h("div", { class: "karte leer" }, "Noch keine Konten. ", h("a", { href: "#/import" }, "KMyMoney-Datei importieren"), " oder ", h("a", { href: "#/konten" }, "Konto anlegen"), ".");
    const [offen, syncStatus, vorschlaege] = await Promise.all([api("GET", "/api/dubletten?status=offen"),
      api("GET", "/api/sync/status"), api("GET", "/api/buchungen?vorschlag=true&pro_seite=1")]);
    const tanOffen = syncStatus.offene_tan_anforderung;
    const letzter = syncStatus.letzter_lauf;
    seite("Finanzübersicht",
      tanOffen ? h("div", { class: "karte hinweis-tan" }, h("strong", null, "TAN erforderlich – "), "die Synchronisation wartet. ",
        h("a", { class: "knopf primaer", href: "#/tan/" + tanOffen.id }, "TAN eingeben")) : null,
      h("div", { class: "werkzeug" },
        h("a", { class: "knopf", href: "#/sync" }, "Synchronisation"),
        h("span", { class: "leise" }, letzter ? ["Letzter Lauf ", zeitText(letzter.gestartet_am), ": ", statusMarke(letzter.status)] : "Noch nicht synchronisiert.")),
      tab,
      vorschlaege.gesamt ? h("p", { class: "karte" }, `${vorschlaege.gesamt} Kategorie-Vorschl${vorschlaege.gesamt === 1 ? "ag" : "äge"} zur Bestätigung – `,
        h("a", { href: "#/buchungen?vorschlag=true" }, "jetzt prüfen")) : null,
      offen.length ? h("p", { class: "karte" }, `${offen.length} Dublettenverdacht${offen.length === 1 ? "" : "e"} zur Bestätigung – `, h("a", { href: "#/import" }, "jetzt prüfen")) : null,
      h("p", { class: "leise" }, "Saldo = Summe aller Splits je Konto. Schulden sind negativ."));
  }

  function kontenTabelle(konten, uebersicht, klickZiel) {
    const sal = new Map(uebersicht.konten.map((k) => [k.konto_id, k]));
    const tbody = h("tbody");
    for (const { konto, tiefe } of baum(konten)) {
      const s = sal.get(konto.id) || { saldo: 0, saldo_gesamt: 0, anzahl_buchungen: 0 };
      const tr = h("tr", { class: "klickbar" + (konto.geschlossen ? " geschlossen" : ""), tabindex: 0, onclick: () => { location.hash = klickZiel + konto.id; } },
        h("td", null, h("span", { class: "einrueck", style: `width:${tiefe * 1.2}rem` }), konto.name, konto.iban ? h("div", { class: "zweck" }, konto.iban) : null),
        h("td", { class: "nur-breit" }, ART_TEXT[konto.art]), betragZelle(s.saldo),
        h("td", { class: "zahl nur-breit" }, betragText(s.saldo_gesamt)), h("td", { class: "zahl leise nur-breit" }, s.anzahl_buchungen));
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") location.hash = klickZiel + konto.id; });
      kontextAuf(tr, (x, y) => menueZeigen(x, y, [
        { text: "Buchungen anzeigen", tun: () => { location.hash = klickZiel + konto.id; } },
        { text: "Bearbeiten …", tun: async () => { if (await kontoDialog(konto)) route(); } },
        { text: "Unterkonto anlegen …", tun: async () => { if (await kontoDialog(null, konto.art)) route(); } },
        "-",
        { text: "Löschen", tun: async () => {
          if (!(await bestaetigen(`Konto „${konto.name}“ löschen?`))) return;
          try { await api("DELETE", `/api/konten/${konto.id}`); melden("Konto gelöscht."); route(); } catch (e) { melden(e.message, true); }
        } },
      ]));
      tbody.append(tr);
    }
    return h("table", { class: "tabelle buchungen" },
      h("thead", null, h("tr", null, h("th", null, "Name"), h("th", { class: "nur-breit" }, "Art"), h("th", { class: "zahl" }, "Saldo"),
        h("th", { class: "zahl nur-breit" }, "inkl. Unterkonten"), h("th", { class: "zahl nur-breit" }, "Buchungen"))), tbody);
  }

  async function ansichtKonten(kategorien) {
    await stammLaden();
    const u = await api("GET", "/api/kontenuebersicht");
    const konten = stamm.konten.filter((k) => (kategorien ? k.ist_kategorie : !k.ist_kategorie));
    const neu = h("button", { type: "button", class: "knopf", onclick: async () => { if (await kontoDialog(null, kategorien ? "aufwand" : "girokonto")) route(); } },
      kategorien ? "+ Kategorie anlegen" : "+ Konto anlegen");
    seite(kategorien ? "Kategorien" : "Konten", h("div", { class: "werkzeug" }, neu, h("span", { class: "leise" }, "Rechtsklick bzw. lange Berührung: Menü")),
      konten.length ? kontenTabelle(konten, u, kategorien ? "#/kategorie/" : "#/konto/") : h("div", { class: "karte leer" }, "Keine Einträge."));
  }

  async function ansichtKonto(id, kategorie) {
    await stammLaden();
    const k = stamm.konten.find((x) => x.id === id);
    if (!k) { seite("Nicht gefunden", h("p", null, "Das Konto existiert nicht.")); return; }
    const sal = (await api("GET", "/api/kontenuebersicht")).konten.find((x) => x.konto_id === id);
    const box = h("div");
    seite((kategorie ? "Kategorie " : "") + kontoPfad(k),
      h("p", { class: "leise" }, ART_TEXT[k.art], k.iban ? " · " + k.iban : "", " · Saldo ", h("strong", null, betragText(sal ? sal.saldo : 0)),
        sal && sal.saldo_gesamt !== sal.saldo ? " · inkl. Unterkonten " + betragText(sal.saldo_gesamt) : "",
        k.geschlossen ? " · geschlossen" : "", " · ", h("a", { href: "javascript:void 0", onclick: async () => { if (await kontoDialog(k)) route(); } }, "bearbeiten")),
      box);
    buchungsliste(box, kategorie ? { kategorie_id: id, unterkategorien: true } : { konto_id: id }, { neu: !kategorie && BESTAND.has(k.art) });
    inhalt._tasten = box._tasten;
  }

  async function ansichtAlleBuchungen(vorschlag) {
    await stammLaden();
    const box = h("div");
    seite("Alle Buchungen", h("p", { class: "leise" }, "Betrag = Umsatz (Summe der positiven Splits). Kategorien mit der Marke „Vorschlag“ stammen aus Regeln und sind noch nicht bestätigt."), box);
    buchungsliste(box, {}, { vorschlag: vorschlag === "true" ? "true" : vorschlag === "false" ? "false" : null });
    inhalt._tasten = box._tasten;
  }

  async function ansichtImport() {
    const datei = h("input", { type: "file", accept: ".kmy,.xml,application/gzip,application/xml", required: true });
    const ausgabe = h("div");
    const form = h("form", { class: "karte" },
      h("p", null, "KMyMoney-Datei (.kmy, gzip-komprimiert oder unkomprimiert) importieren. Ein erneuter Import derselben Datei ändert nichts; erweiterte Fassungen fügen nur Neues hinzu."),
      h("div", { class: "werkzeug" }, datei, h("button", { type: "submit", class: "knopf primaer" }, "Importieren")), ausgabe);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!datei.files.length) return;
      const fd = new FormData();
      fd.append("datei", datei.files[0], datei.files[0].name);
      ausgabe.replaceChildren(h("p", { class: "leise" }, "Import läuft …"));
      let erg;
      try { erg = await api("POST", "/api/import/kmymoney", undefined, fd); }
      catch (err) {
        const d = err.details || {};
        ausgabe.replaceChildren(h("p", { class: "negativ" }, "Import fehlgeschlagen – es wurde nichts übernommen."),
          h("ul", null, (d.fehler || [{ meldung: err.message }]).map((f) => h("li", null, f.meldung, f.referenz ? ` (${f.referenz})` : ""))));
        return;
      }
      ausgabe.replaceChildren(ergebnisAnzeige(erg));
      melden("Import erfolgreich.");
      stammLaden();
      verdachteZeichnen();
      importeZeichnen();
    });
    const verdachte = h("div");
    const importe = h("div");
    async function verdachteZeichnen() {
      await stammLaden();
      const liste = await api("GET", "/api/dubletten?status=offen");
      if (!liste.length) { verdachte.replaceChildren(h("p", { class: "leise" }, "Keine offenen Dublettenverdachte.")); return; }
      const ids = [...new Set(liste.flatMap((v) => [v.buchung_id, ...v.kandidat_ids]))];
      const buchungen = new Map();
      await Promise.all(ids.map(async (id) => { try { buchungen.set(id, await api("GET", `/api/buchungen/${id}`)); } catch (e) { /* gelöscht */ } }));
      const kurz = (b) => b ? `#${b.id} · ${datumText(b.datum)} · ${b.empfaenger ? b.empfaenger.name : "ohne Empfänger"} · ${betragText(b.betrag)}${b.verwendungszweck ? " · " + b.verwendungszweck.slice(0, 60) : ""}` : "(nicht mehr vorhanden)";
      verdachte.replaceChildren(...liste.map((v) => h("div", { class: "karte" },
        h("div", null, h("strong", null, v.grund === "mehrdeutig" ? "Mehrdeutige Dublette" : "Ähnliche Buchung"), " – importiert: ", kurz(buchungen.get(v.buchung_id))),
        h("ul", null, v.kandidat_ids.map((c) => h("li", null, kurz(buchungen.get(c)), " ",
          h("button", { type: "button", class: "knopf", onclick: async () => {
            try { await api("POST", `/api/dubletten/${v.id}/aufloesen`, { entscheidung: "zusammenfuehren", behalten_id: c }); melden("Zusammengeführt."); verdachteZeichnen(); } catch (e) { melden(e.message, true); }
          } }, "Zusammenführen (diese behalten)")))),
        h("button", { type: "button", class: "knopf", onclick: async () => {
          try { await api("POST", `/api/dubletten/${v.id}/aufloesen`, { entscheidung: "keine_dublette" }); melden("Als eigenständige Buchung bestätigt."); verdachteZeichnen(); } catch (e) { melden(e.message, true); }
        } }, "Keine Dublette"))));
    }
    async function importeZeichnen() {
      const liste = await api("GET", "/api/importe");
      importe.replaceChildren(liste.length ? h("table", { class: "tabelle" },
        h("thead", null, h("tr", null, h("th", null, "#"), h("th", null, "Datei"), h("th", { class: "nur-breit" }, "Zeitpunkt (UTC)"), h("th", { class: "zahl" }, "neu"), h("th", { class: "zahl" }, "vorhanden"))),
        h("tbody", null, liste.slice().reverse().map((i) => h("tr", null, h("td", null, i.id), h("td", null, i.dateiname || "–"), h("td", { class: "nur-breit" }, i.importiert_am.replace("T", " ").replace("Z", "")),
          h("td", { class: "zahl" }, i.ergebnis.buchungen_neu), h("td", { class: "zahl" }, i.ergebnis.buchungen_vorhanden))))) : h("p", { class: "leise" }, "Noch keine Importe."));
    }
    seite("Import", form, h("h2", null, "Dublettenverdachte"), verdachte, h("h2", null, "Bisherige Importe"), importe,
      h("p", { class: "leise" }, "GnuCash-Import folgt später."));
    verdachteZeichnen();
    importeZeichnen();
  }

  function ergebnisAnzeige(e) {
    const zeilen = [["Konten neu / vorhanden", e.konten_neu + " / " + e.konten_vorhanden], ["Kategorien neu / vorhanden", e.kategorien_neu + " / " + e.kategorien_vorhanden],
      ["Empfänger neu / vorhanden", e.empfaenger_neu + " / " + e.empfaenger_vorhanden], ["Tags neu / vorhanden", e.tags_neu + " / " + e.tags_vorhanden],
      ["Buchungen neu", e.buchungen_neu], ["Buchungen bereits vorhanden", e.buchungen_vorhanden], ["Als Dublette zusammengeführt", e.buchungen_zusammengefuehrt],
      ["Zur Prüfung vorgelegt", e.buchungen_zur_pruefung], ["Übersprungen", e.buchungen_uebersprungen], ["Splits neu", e.splits_neu]];
    return h("div", null, h("p", { class: "positiv" }, `Import erfolgreich (${e.format}).`),
      h("ul", { class: "ergebnis-liste" }, zeilen.map(([a, b]) => h("li", null, a + ": ", h("strong", null, b)))),
      e.warnungen.length ? h("details", null, h("summary", null, `${e.warnungen.length} Hinweis(e)`),
        h("ul", null, e.warnungen.map((w) => h("li", null, w.meldung, w.referenz ? ` (${w.referenz})` : "")))) : null);
  }

  async function ansichtEinstellungen() {
    await stammLaden();
    const status = await api("GET", "/api/status");
    const tagsBox = h("div");
    const zeichneTags = async () => {
      await stammLaden();
      const neu = h("input", { type: "text", placeholder: "Neuer Tag", maxlength: 100 });
      tagsBox.replaceChildren(
        h("table", { class: "tabelle" }, h("thead", null, h("tr", null, h("th", null, "Tag"), h("th", { class: "zahl" }, "Buchungen"), h("th", null, ""))),
          h("tbody", null, stamm.tags.map((t) => h("tr", null, h("td", null, t.name), h("td", { class: "zahl" }, t.anzahl_buchungen),
            h("td", null, h("button", { type: "button", class: "knopf", onclick: async () => {
              const feld = h("input", { type: "text", value: t.name, maxlength: 100 });
              const name = await dialog("Tag umbenennen", h("label", { class: "feld" }, "Name", feld), [{ text: "Umbenennen", klasse: "primaer", submit: true, tun: () => feld.value }]);
              if (name === null) return;
              try { await api("PATCH", `/api/tags/${t.id}`, { name }); zeichneTags(); } catch (e) { melden(e.message, true); }
            } }, "Umbenennen"), " ",
            h("button", { type: "button", class: "knopf gefahr", onclick: async () => {
              if (!(await bestaetigen(`Tag „${t.name}“ löschen? Die Buchungen bleiben erhalten.`))) return;
              try { await api("DELETE", `/api/tags/${t.id}`); zeichneTags(); } catch (e) { melden(e.message, true); }
            } }, "Löschen")))))),
        h("form", { class: "werkzeug", onsubmit: async (e) => { e.preventDefault(); try { await api("POST", "/api/tags", { name: neu.value }); zeichneTags(); } catch (err) { melden(err.message, true); } } },
          neu, h("button", { type: "submit", class: "knopf" }, "Anlegen")));
    };
    seite("Einstellungen",
      h("div", { class: "karte" }, h("h2", { style: "margin-top:0" }, "Betrieb"),
        h("ul", null, h("li", null, "Modus: ", h("strong", null, status.modus === "mock" ? "Mock-Modus" : "Echtbetrieb")),
          status.hinweis ? h("li", null, status.hinweis) : null,
          status.mock_szenario ? h("li", null, "Mock-Szenario: ", status.mock_szenario) : null,
          h("li", null, `Bank-Plugin: ${status.plugins.bank.name}${status.plugins.bank.mock ? " (Mock)" : ""}`),
          h("li", null, `Mail-Plugin: ${status.plugins.mail.name}${status.plugins.mail.mock ? " (Mock)" : ""}`),
          h("li", null, "Version: ", status.version)),
        h("p", { class: "leise" }, "Bank-Synchronisation, PIN und Mock-Uhr: ", h("a", { href: "#/sync" }, "Synchronisation"), ". Zustellung per ntfy und Login folgen in späteren Meilensteinen.")),
      h("h2", null, "Tags"), tagsBox,
      h("h2", null, "Empfänger"),
      stamm.empfaenger.length ? h("ul", null, stamm.empfaenger.map((e) => h("li", null, e.name))) : h("p", { class: "leise" }, "Keine Empfänger."),
      h("h2", null, "Darstellung"),
      h("p", null, "Helles oder dunkles Design folgt der Systemeinstellung. ",
        h("button", { type: "button", class: "knopf", onclick: () => { localStorage.removeItem(LAYOUT); document.documentElement.style.removeProperty("--nav-breite"); rahmen.classList.remove("nav-zu"); melden("Layout zurückgesetzt."); } }, "Layout zurücksetzen")));
    zeichneTags();
  }

  // ------------------------------------------------- Synchronisation (M2)
  const LAUF_TEXT = { laeuft: "läuft", erfolgreich: "erfolgreich", fehlgeschlagen: "fehlgeschlagen",
    wartet_auf_tan: "wartet auf TAN", abgebrochen: "abgebrochen", ausstehend: "ausstehend" };
  const TAN_TEXT = { offen: "offen", beantwortet: "beantwortet", abgelaufen: "abgelaufen", abgebrochen: "abgebrochen" };

  function zeitText(iso) {
    if (!iso) return "–";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
  }

  function statusMarke(status, text) {
    return h("span", { class: "marke-status lauf-" + status }, text || LAUF_TEXT[status] || status);
  }

  /** Zählt ungelesene Benachrichtigungen und zeigt sie im Kopf (Glocke). */
  async function glockeAktualisieren() {
    try {
      const offen = await api("GET", "/api/benachrichtigungen?gelesen=false");
      const g = $("#glocke");
      g.querySelector(".zahl-marke").textContent = offen.length ? String(offen.length) : "";
      g.classList.toggle("aktiv", offen.length > 0);
      g.title = offen.length ? `${offen.length} ungelesene Benachrichtigung(en)` : "Benachrichtigungen";
    } catch (e) { /* Kopf bleibt unverändert */ }
  }

  function laufZeile(l) {
    const konten = h("ul", { class: "lauf-konten" }, l.konten.map((k) => {
      const konto = kontoNach(k.konto_id);
      return h("li", null, statusMarke(k.status), " ", konto ? konto.name : "Konto #" + k.konto_id, " ",
        h("span", { class: "leise" }, k.iban), k.konto_neu ? h("span", { class: "tag" }, "neu angelegt") : null,
        k.von ? h("span", { class: "leise" }, ` · ${datumText(k.von)} – ${datumText(k.bis)}`) : null,
        k.status === "erfolgreich" ? h("div", { class: "zweck" },
          `${k.umsaetze_gesamt} Umsätze: ${k.buchungen_neu} neu (davon ${k.buchungen_kategorisiert} per Regel kategorisiert, `
          + `${k.buchungen_zur_pruefung} zur Prüfung), ${k.buchungen_vorhanden} bereits vorhanden, `
          + `${k.buchungen_zusammengefuehrt} mit Vorhandenem zusammengeführt, ${k.vormerkungen_ignoriert} Vormerkungen`) : null,
        k.fehler ? h("div", { class: "zweck negativ" }, k.fehler.meldung, " (", k.fehler.code, ")") : null);
    }));
    return h("tr", null, h("td", null, "#" + l.id), h("td", null, zeitText(l.gestartet_am), h("div", { class: "zweck" }, l.ausloeser === "planer" ? "automatisch" : "manuell")),
      h("td", null, statusMarke(l.status),
        l.status === "wartet_auf_tan" && l.tan_anforderung_id ? h("div", null, h("a", { href: "#/tan/" + l.tan_anforderung_id }, "TAN eingeben …")) : null,
        l.fehler ? h("div", { class: "zweck negativ" }, l.fehler.meldung) : null),
      h("td", null, l.konten.length ? konten : h("span", { class: "leise" }, "–")));
  }

  async function ansichtSync() {
    await stammLaden();
    const [st, laeufe, zustaende, status] = await Promise.all([api("GET", "/api/sync/status"), api("GET", "/api/sync/laeufe"),
      api("GET", "/api/sync/konten"), api("GET", "/api/status")]);
    const offen = st.offene_tan_anforderung;
    const von = h("input", { type: "date", "aria-label": "Zeitraum von" });
    const bis = h("input", { type: "date", "aria-label": "Zeitraum bis" });
    const startKnopf = h("button", { type: "submit", class: "knopf primaer", disabled: !!offen || st.laeuft }, "Jetzt synchronisieren");
    const startForm = h("form", { class: "werkzeug" }, startKnopf,
      h("details", { class: "zeitraum" }, h("summary", null, "Zeitraum wählen"),
        h("div", { class: "werkzeug" }, h("label", { class: "feld" }, "von", von), h("label", { class: "feld" }, "bis", bis),
          h("span", { class: "leise" }, "leer = automatisch (seit letztem Abruf mit Überlappung)"))));
    startForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const koerper = {};
      if (von.value) koerper.von = von.value;
      if (bis.value) koerper.bis = bis.value;
      startKnopf.disabled = true;
      startKnopf.textContent = "Synchronisiere …";
      try {
        const lauf = await api("POST", "/api/sync", koerper);
        if (lauf.status === "wartet_auf_tan") { melden("Die Bank verlangt eine TAN."); location.hash = "#/tan/" + lauf.tan_anforderung_id; return; }
        const neu = lauf.konten.reduce((s, k) => s + k.buchungen_neu, 0);
        melden(lauf.status === "erfolgreich" ? `Synchronisation erfolgreich: ${neu} neue Buchung(en).` : `Synchronisation ${LAUF_TEXT[lauf.status]}: ${lauf.fehler ? lauf.fehler.meldung : ""}`,
          lauf.status !== "erfolgreich");
      } catch (err) { melden(err.message, true); }
      glockeAktualisieren();
      route();
    });

    const pin = h("input", { class: "eingabe", type: "password", autocomplete: "off", maxlength: 128, placeholder: "Banking-PIN", "aria-label": "Banking-PIN", name: "pin-eingabe" });
    const pinForm = h("form", { class: "werkzeug" }, pin, h("button", { type: "submit", class: "knopf" }, "PIN übernehmen"),
      h("button", { type: "button", class: "knopf", disabled: !st.pin_vorhanden, onclick: async () => {
        try { await api("DELETE", "/api/sync/pin"); melden("PIN verworfen."); route(); } catch (err) { melden(err.message, true); }
      } }, "PIN verwerfen"));
    pinForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const wert = pin.value;
      pin.value = "";
      if (!wert) return;
      try { await api("PUT", "/api/sync/pin", { pin: wert }); melden("PIN im Arbeitsspeicher abgelegt."); route(); }
      catch (err) { melden(err.message, true); }
    });

    let uhr = null;
    if (status.mock) {
      const z = await api("GET", "/api/mock/zeit");
      const feld = h("input", { type: "datetime-local", step: 1, value: z.jetzt.replace("Z", ""), "aria-label": "Simulierte Zeit (UTC)" });
      const form = h("form", { class: "werkzeug" }, h("label", { class: "feld" }, "Simulierte Zeit (UTC)", feld),
        h("button", { type: "submit", class: "knopf" }, "Zeit setzen"),
        h("button", { type: "button", class: "knopf", onclick: async () => {
          const d = new Date(z.jetzt);
          d.setUTCDate(d.getUTCDate() + 1);
          await api("PUT", "/api/mock/zeit", { jetzt: d.toISOString().replace(/\.\d{3}Z$/, "Z") }); route();
        } }, "+1 Tag"));
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        let w = feld.value;
        if (w.length === 16) w += ":00";
        try { await api("PUT", "/api/mock/zeit", { jetzt: w + "Z" }); melden("Simulierte Zeit gesetzt."); route(); }
        catch (err) { melden(err.message, true); }
      });
      uhr = h("div", { class: "karte" }, h("h2", { class: "oben" }, "Mock-Uhr"),
        h("p", null, "Heute (simuliert): ", h("strong", null, datumText(z.heute)), z.simuliert ? "" : " (Systemzeit)"),
        form, h("p", { class: "leise" }, "Die Mock-Bank liefert nur Umsätze bis zu diesem Tag; rückt die Zeit vor, erscheinen neue."));
    }

    const kontenTab = zustaende.length ? h("table", { class: "tabelle" },
      h("thead", null, h("tr", null, h("th", null, "Konto"), h("th", { class: "nur-breit" }, "IBAN"), h("th", null, "abgerufen bis"), h("th", { class: "nur-breit" }, "letzter Erfolg"))),
      h("tbody", null, zustaende.map((z) => {
        const k = kontoNach(z.konto_id);
        return h("tr", { class: "klickbar", onclick: () => { location.hash = "#/konto/" + z.konto_id; } },
          h("td", null, k ? k.name : "#" + z.konto_id), h("td", { class: "nur-breit" }, z.iban),
          h("td", null, z.letzter_abruf_bis ? datumText(z.letzter_abruf_bis) : "–"), h("td", { class: "nur-breit" }, zeitText(z.letzter_erfolg_am)));
      }))) : h("p", { class: "leise" }, "Noch kein Bankkonto zugeordnet. Der erste Lauf ordnet die Bankkonten über die IBAN zu (fehlende werden angelegt).");

    seite("Synchronisation",
      offen ? h("div", { class: "karte hinweis-tan" }, h("strong", null, "TAN erforderlich: "), offen.challenge, " ",
        h("a", { class: "knopf primaer", href: "#/tan/" + offen.id }, "Zur TAN-Seite")) : null,
      h("div", { class: "karte" },
        h("ul", { class: "eckdaten" },
          h("li", null, "Automatischer Abruf: ", h("strong", null, st.automatisch ? `alle ${st.intervall_minuten} Minuten` : "aus")),
          h("li", null, "Nächster Lauf: ", h("strong", null, st.naechster_lauf ? zeitText(st.naechster_lauf) : "–")),
          h("li", null, "Letzter Lauf: ", st.letzter_lauf ? [statusMarke(st.letzter_lauf.status), " ", zeitText(st.letzter_lauf.gestartet_am)] : h("strong", null, "noch keiner")),
          h("li", null, "PIN: ", h("strong", null, st.pin_vorhanden ? "im Arbeitsspeicher" : "nicht hinterlegt"))),
        startForm),
      h("div", { class: "karte" }, h("h2", { class: "oben" }, "Banking-PIN"),
        h("p", { class: "leise" }, "Die PIN wird nur im Arbeitsspeicher gehalten – nie gespeichert, nie protokolliert – und ist nach einem Neustart weg. Lehnt die Bank sie ab, wird sie sofort verworfen."),
        pinForm),
      uhr,
      h("h2", null, "Bankkonten"), kontenTab,
      h("h2", null, "Läufe"),
      laeufe.length ? h("table", { class: "tabelle" },
        h("thead", null, h("tr", null, h("th", null, "#"), h("th", null, "Start"), h("th", null, "Status"), h("th", null, "Konten"))),
        h("tbody", null, laeufe.slice().reverse().slice(0, 50).map(laufZeile))) : h("p", { class: "leise" }, "Noch keine Läufe."));
  }

  // ---------------------------------------------------------- TAN-Seite (K 6)
  async function ansichtTan(id) {
    let t;
    try { t = await api("GET", `/api/tan-anforderungen/${id}`); }
    catch (e) { seite("TAN-Anforderung", h("p", { class: "negativ" }, e.message)); return; }
    await stammLaden();
    const konto = kontoNach(t.konto_id);
    const kopf = h("p", null, "Konto: ", h("strong", null, konto ? konto.name : t.iban), " · ", t.iban, " · ", statusMarke(t.status, TAN_TEXT[t.status]));
    if (t.status !== "offen") {
      seite("TAN-Anforderung", kopf,
        h("div", { class: "karte" }, t.status === "beantwortet" ? "Die TAN wurde angenommen, die Synchronisation ist weitergelaufen."
          : t.status === "abgelaufen" ? "Die TAN-Anforderung ist abgelaufen. Starte die Synchronisation neu, um eine neue Anforderung zu erhalten."
            : "Die TAN-Anforderung wurde abgebrochen."),
        h("a", { class: "knopf", href: "#/sync" }, "Zur Synchronisation"));
      return;
    }
    const bildUrl = `/api/tan-anforderungen/${t.id}/bild`;
    let blob = null;
    const bildBox = h("div", { class: "tan-bild" });
    if (t.hat_bild) {
      try {
        const r = await fetch(bildUrl, { cache: "no-store" });
        if (r.ok) blob = await r.blob();
      } catch (e) { blob = null; }
    }
    const dateiname = `tan-qr-${t.id}.png`;
    if (blob) {
      const url = URL.createObjectURL(blob);
      bildBox.append(h("img", { src: url, alt: "QR-Code der TAN-Anforderung", width: 264, height: 264 }));
      const speichern = h("a", { class: "knopf", href: url, download: dateiname }, "QR-Code speichern");
      let datei = null;
      try { datei = new File([blob], dateiname, { type: blob.type || "image/png" }); } catch (e) { datei = null; }
      const teilenMoeglich = datei && navigator.canShare && navigator.canShare({ files: [datei] });
      const teilen = h("button", { type: "button", class: "knopf", disabled: !teilenMoeglich,
        title: teilenMoeglich ? "Bild an die Banking-App übergeben" : "Teilen wird von diesem Browser nicht unterstützt – bitte speichern",
        onclick: async () => {
          try { await navigator.share({ files: [datei], title: "TAN-QR-Code" }); } catch (e) { if (e.name !== "AbortError") melden(e.message, true); }
        } }, "Teilen …");
      bildBox.append(h("div", { class: "werkzeug" }, speichern, teilen));
    } else {
      bildBox.append(h("p", { class: "leise" }, "Kein Bild vorhanden – bitte der Anweisung folgen."));
    }
    const tan = h("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 64, required: true, "aria-label": "TAN", class: "tan-feld" });
    const senden = h("button", { type: "submit", class: "knopf primaer" }, "TAN senden");
    const form = h("form", { class: "werkzeug" }, h("label", { class: "feld" }, "TAN", tan), senden,
      h("button", { type: "button", class: "knopf gefahr", onclick: async () => {
        if (!(await bestaetigen("TAN-Anforderung abbrechen? Die Synchronisation wird abgebrochen."))) return;
        try { await api("POST", `/api/tan-anforderungen/${t.id}/abbrechen`); melden("TAN-Anforderung abgebrochen."); } catch (e) { melden(e.message, true); }
        glockeAktualisieren(); route();
      } }, "Abbrechen"));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const wert = tan.value.trim();
      tan.value = "";
      if (!wert) return;
      senden.disabled = true;
      try {
        const lauf = await api("POST", `/api/tan-anforderungen/${t.id}/antwort`, { tan: wert });
        if (lauf.status === "wartet_auf_tan" && lauf.tan_anforderung_id !== t.id) {
          melden("TAN angenommen. Ein weiteres Konto verlangt eine TAN.");
          location.hash = "#/tan/" + lauf.tan_anforderung_id;
          return;
        }
        melden(`TAN angenommen. Synchronisation ${LAUF_TEXT[lauf.status]}.`, lauf.status === "fehlgeschlagen");
        glockeAktualisieren();
        location.hash = "#/sync";
      } catch (err) {
        senden.disabled = false;
        melden(err.code === "tan_ungueltig" ? "Die TAN wurde nicht akzeptiert. Bitte erneut versuchen." : err.message, true);
        if (err.code !== "tan_ungueltig") route();
      }
    });
    seite("TAN-Freigabe", kopf,
      h("div", { class: "karte tan-karte" },
        h("p", { class: "challenge" }, t.challenge), bildBox,
        h("p", { class: "leise" }, "Den QR-Code mit der Banking-App scannen (z. B. am zweiten Bildschirm). Nur am Handy: Bild speichern oder teilen und in der Banking-App öffnen."),
        form,
        h("p", { class: "leise" }, "Gültig bis ", zeitText(t.gueltig_bis), ".")));
    tan.focus();
  }

  // ------------------------------------------------------ Benachrichtigungen
  async function ansichtBenachrichtigungen() {
    const liste = await api("GET", "/api/benachrichtigungen");
    const zeile = (b) => h("li", { class: "karte benachrichtigung" + (b.gelesen ? " gelesen" : "") },
      h("div", null, h("strong", null, b.titel), " ", h("span", { class: "leise" }, zeitText(b.erstellt_am))),
      h("div", null, b.text),
      h("div", { class: "werkzeug" },
        b.link ? h("a", { class: "knopf primaer", href: "#" + b.link }, "Öffnen") : null,
        b.gelesen ? h("span", { class: "leise" }, "gelesen") : h("button", { type: "button", class: "knopf", onclick: async () => {
          try { await api("POST", `/api/benachrichtigungen/${b.id}/gelesen`); glockeAktualisieren(); route(); } catch (e) { melden(e.message, true); }
        } }, "Als gelesen markieren")));
    const ungelesen = liste.filter((b) => !b.gelesen);
    seite("Benachrichtigungen",
      ungelesen.length > 1 ? h("div", { class: "werkzeug" }, h("button", { type: "button", class: "knopf", onclick: async () => {
        for (const b of ungelesen) { try { await api("POST", `/api/benachrichtigungen/${b.id}/gelesen`); } catch (e) { /* weiter */ } }
        glockeAktualisieren(); route();
      } }, "Alle als gelesen markieren")) : null,
      liste.length ? h("ul", { class: "liste-ohne" }, liste.slice().reverse().map(zeile)) : h("div", { class: "karte leer" }, "Keine Benachrichtigungen."));
    glockeAktualisieren();
  }

  // ------------------------------------------------------------ Regeln (K 7)
  const FELD_TEXT = { empfaenger: "Empfänger", verwendungszweck: "Verwendungszweck", betrag: "Betrag", konto_id: "Konto" };
  const OP_TEXT = { enthaelt: "enthält", gleich: "ist gleich", beginnt_mit: "beginnt mit", mindestens: "mindestens", hoechstens: "höchstens" };
  const OPS = { empfaenger: ["enthaelt", "gleich", "beginnt_mit"], verwendungszweck: ["enthaelt", "gleich", "beginnt_mit"],
    betrag: ["gleich", "mindestens", "hoechstens"], konto_id: ["gleich"] };

  function bedingungText(b) {
    const wert = b.feld === "betrag" ? betragText(b.wert) : b.feld === "konto_id" ? (kontoNach(b.wert) || { name: "#" + b.wert }).name : `„${b.wert}“`;
    return `${FELD_TEXT[b.feld]} ${OP_TEXT[b.operator]} ${wert}`;
  }

  function bedingungZeile(b, entfernen) {
    const feld = h("select", { "aria-label": "Feld" }, Object.keys(FELD_TEXT).map((f) => h("option", { value: f, selected: b && b.feld === f }, FELD_TEXT[f])));
    const op = h("select", { "aria-label": "Operator" });
    const wertBox = h("span", { class: "bed-wert" });
    let wert = null;
    const zeichne = (vorgabe) => {
      const f = feld.value;
      op.replaceChildren(...OPS[f].map((o) => h("option", { value: o, selected: vorgabe && vorgabe.operator === o }, OP_TEXT[o])));
      if (f === "konto_id") wert = h("select", { "aria-label": "Wert" }, kontoOptionen(vorgabe ? vorgabe.wert : null, (k) => BESTAND.has(k.art)));
      else if (f === "betrag") wert = h("input", { type: "text", inputmode: "decimal", placeholder: "z. B. -50,01", "aria-label": "Wert", value: vorgabe ? betragText(vorgabe.wert, false) : "" });
      else wert = h("input", { type: "text", maxlength: 200, placeholder: "Text", "aria-label": "Wert", value: vorgabe ? vorgabe.wert : "" });
      wertBox.replaceChildren(wert);
    };
    feld.addEventListener("change", () => zeichne(null));
    zeichne(b);
    const zeile = h("div", { class: "bed-zeile" }, feld, op, wertBox,
      h("button", { type: "button", class: "knopf", "aria-label": "Bedingung entfernen", onclick: () => entfernen(zeile) }, "×"));
    zeile._lesen = () => {
      const f = feld.value;
      if (f === "betrag") { const c = betragLesen(wert.value); if (c === null) throw new Error("Ungültiger Betrag in einer Bedingung."); return { feld: f, operator: op.value, wert: c }; }
      if (f === "konto_id") return { feld: f, operator: "gleich", wert: Number(wert.value) };
      return { feld: f, operator: op.value, wert: wert.value };
    };
    return zeile;
  }

  async function regelDialog(r) {
    await stammLaden();
    const name = h("input", { type: "text", maxlength: 200, required: true, value: r ? r.name : "" });
    const kat = h("select", { required: true }, kategorieOptionen(r ? r.kategorie_id : null, "– Kategorie wählen –"));
    const prio = h("input", { type: "number", min: 0, max: 1000000, step: 1, value: r ? r.prioritaet : "", placeholder: "automatisch" });
    const aktiv = h("input", { type: "checkbox", checked: r ? r.aktiv : true });
    const beds = h("div", { class: "bed-liste" });
    const entfernen = (z) => { if (beds.children.length > 1) z.remove(); };
    (r ? r.bedingungen : [{ feld: "empfaenger", operator: "enthaelt", wert: "" }]).forEach((b) => beds.append(bedingungZeile(b, entfernen)));
    const inhaltBox = h("div", null,
      h("label", { class: "feld" }, "Name", name),
      h("label", { class: "feld" }, "Kategorie", kat),
      h("div", { class: "feld" }, "Bedingungen (alle müssen zutreffen)", beds,
        h("button", { type: "button", class: "knopf", onclick: () => { if (beds.children.length < 20) beds.append(bedingungZeile(null, entfernen)); } }, "+ Bedingung")),
      h("label", { class: "feld" }, "Priorität (kleiner = wichtiger)", prio),
      h("label", { class: "feld zeile" }, aktiv, "aktiv"));
    return dialog(r ? "Regel bearbeiten" : "Neue Regel", inhaltBox, [{ text: r ? "Speichern" : "Anlegen", klasse: "primaer", submit: true, tun: async () => {
      const koerper = { name: name.value, kategorie_id: Number(kat.value), aktiv: aktiv.checked,
        bedingungen: [...beds.children].map((z) => z._lesen()) };
      if (prio.value !== "") koerper.prioritaet = Number(prio.value);
      if (!kat.value) throw new Error("Bitte eine Kategorie wählen.");
      return r ? api("PATCH", `/api/regeln/${r.id}`, koerper) : api("POST", "/api/regeln", koerper);
    } }]);
  }

  async function ansichtRegeln() {
    await stammLaden();
    const liste = await api("GET", "/api/regeln");
    const ergebnis = h("div");
    const nurUnk = h("input", { type: "checkbox", checked: true });
    async function anwenden(trocken) {
      try {
        const e = await api("POST", "/api/regeln/anwenden", { nur_unkategorisiert: nurUnk.checked, trocken });
        const regelName = new Map(liste.map((r) => [r.id, r.name]));
        ergebnis.replaceChildren(h("div", { class: "karte" },
          h("p", null, `${e.geprueft} Buchung(en) geprüft, ${e.anzahl} ${trocken ? "würden" : "wurden"} als Vorschlag kategorisiert.`),
          e.aenderungen.length ? h("ul", null, e.aenderungen.slice(0, 100).map((a) => h("li", null,
            h("a", { href: "javascript:void 0", onclick: async () => { const b = await api("GET", `/api/buchungen/${a.buchung_id}`); if (await buchungDialog(b)) route(); } }, "Buchung #" + a.buchung_id),
            " → ", (kontoNach(a.kategorie_id) || { name: "#" + a.kategorie_id }).name, h("span", { class: "leise" }, " (", regelName.get(a.regel_id) || "#" + a.regel_id, ")")))) : null,
          trocken && e.anzahl ? h("button", { type: "button", class: "knopf primaer", onclick: () => anwenden(false) }, "Jetzt anwenden") : null,
          !trocken && e.anzahl ? h("a", { class: "knopf", href: "#/buchungen?vorschlag=true" }, "Vorschläge prüfen") : null));
        if (!trocken) melden(`${e.anzahl} Vorschlag/Vorschläge gesetzt.`);
      } catch (err) { melden(err.message, true); }
    }
    const tab = liste.length ? h("table", { class: "tabelle regeln" },
      h("thead", null, h("tr", null, h("th", { class: "zahl" }, "Prio"), h("th", null, "Name"), h("th", null, "Bedingungen"), h("th", null, "Kategorie"), h("th", null, ""))),
      h("tbody", null, liste.map((r) => h("tr", { class: r.aktiv ? "" : "geschlossen" },
        h("td", { class: "zahl" }, r.prioritaet),
        h("td", null, r.name, r.aktiv ? null : h("span", { class: "leise" }, " (inaktiv)")),
        h("td", null, h("ul", { class: "liste-ohne" }, r.bedingungen.map((b) => h("li", null, bedingungText(b))))),
        h("td", null, (kontoNach(r.kategorie_id) || { name: "#" + r.kategorie_id }).name),
        h("td", { class: "aktionen" },
          h("button", { type: "button", class: "knopf", onclick: async () => { if (await regelDialog(r)) route(); } }, "Bearbeiten"), " ",
          h("button", { type: "button", class: "knopf", onclick: async () => {
            try { await api("PATCH", `/api/regeln/${r.id}`, { aktiv: !r.aktiv }); route(); } catch (e) { melden(e.message, true); }
          } }, r.aktiv ? "Deaktivieren" : "Aktivieren"), " ",
          h("button", { type: "button", class: "knopf gefahr", onclick: async () => {
            if (!(await bestaetigen(`Regel „${r.name}“ löschen? Bereits gesetzte Vorschläge bleiben erhalten.`))) return;
            try { await api("DELETE", `/api/regeln/${r.id}`); melden("Regel gelöscht."); route(); } catch (e) { melden(e.message, true); }
          } }, "Löschen")))))) : h("div", { class: "karte leer" }, "Noch keine Regeln.");
    seite("Regeln",
      h("p", { class: "leise" }, "Feste Zuordnungen, z. B. „Empfänger enthält REWE → Lebensmittel“. Neue Buchungen aus der Synchronisation werden automatisch kategorisiert; die erste passende aktive Regel (Priorität, dann Reihenfolge) gewinnt. Gesetzte Kategorien bleiben als Vorschlag markiert, bis sie bestätigt sind."),
      h("div", { class: "werkzeug" }, h("button", { type: "button", class: "knopf primaer", onclick: async () => { if (await regelDialog(null)) route(); } }, "+ Regel anlegen")),
      tab,
      h("h2", null, "Auf vorhandene Buchungen anwenden"),
      h("div", { class: "karte" },
        h("label", { class: "feld zeile" }, nurUnk, "nur unkategorisierte Buchungen (abgeglichene werden nie geändert)"),
        h("div", { class: "werkzeug" },
          h("button", { type: "button", class: "knopf", onclick: () => anwenden(true) }, "Probelauf"),
          h("button", { type: "button", class: "knopf primaer", onclick: () => anwenden(false) }, "Anwenden"))),
      ergebnis);
  }

  const SPAETER = { wiederkehrend: "Wiederkehrende Buchungen", kredite: "Kredite", berichte: "Berichte" };

  function ansichtSpaeter(name) {
    seite(SPAETER[name] || "Später", h("div", { class: "karte leer" }, "Dieser Bereich wird in einem späteren Meilenstein umgesetzt."));
  }

  // ------------------------------------------------------------ Router
  async function route() {
    menueSchliessen();
    navUmschalten(false);
    glockeAktualisieren();
    const [pfadTeil, suchTeil] = (location.hash.replace(/^#\/?/, "") || "uebersicht").split("?");
    const teile = pfadTeil.split("/");
    const hashParameter = new URLSearchParams(suchTeil || "");
    const [bereich, arg] = teile;
    for (const a of document.querySelectorAll(".navigation a")) {
      const b = a.dataset.bereich;
      a.classList.toggle("aktiv", b === bereich || (bereich === "konto" && b === "konten") || (bereich === "kategorie" && b === "kategorien") || (bereich === "spaeter" && b === arg));
    }
    try {
      if (bereich === "uebersicht") { await stammLaden(); await ansichtUebersicht(); }
      else if (bereich === "konten") await ansichtKonten(false);
      else if (bereich === "kategorien") await ansichtKonten(true);
      else if (bereich === "konto") await ansichtKonto(Number(arg), false);
      else if (bereich === "kategorie") await ansichtKonto(Number(arg), true);
      else if (bereich === "buchungen") await ansichtAlleBuchungen(hashParameter.get("vorschlag"));
      else if (bereich === "sync") await ansichtSync();
      else if (bereich === "tan") await ansichtTan(Number(arg));
      else if (bereich === "regeln") await ansichtRegeln();
      else if (bereich === "benachrichtigungen") await ansichtBenachrichtigungen();
      else if (bereich === "import") await ansichtImport();
      else if (bereich === "einstellungen") await ansichtEinstellungen();
      else if (bereich === "spaeter") ansichtSpaeter(arg);
      else seite("Nicht gefunden", h("p", null, "Diese Seite gibt es nicht."));
    } catch (e) {
      seite("Fehler", h("p", { class: "negativ" }, e.message));
    }
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { menueSchliessen(); navUmschalten(false); }
    if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      const f = $("#freitext");
      if (f) { e.preventDefault(); f.focus(); }
    }
    if (inhalt._tasten && huelle.hidden) inhalt._tasten(e);
  });
  $("#menue-knopf").addEventListener("click", () => navUmschalten());
  $("#schleier").addEventListener("click", () => navUmschalten(false));
  window.addEventListener("hashchange", route);
  const tanPfad = /^\/tan\/(\d+)\/?$/.exec(location.pathname);
  if (tanPfad) history.replaceState(null, "", "/#/tan/" + tanPfad[1]);
  $("#glocke").addEventListener("click", () => { location.hash = "#/benachrichtigungen"; });
  glockeAktualisieren();
  setInterval(() => { if (!document.hidden) glockeAktualisieren(); }, 30000);
  layoutLaden();
  trennerEinrichten();
  route();
})();
