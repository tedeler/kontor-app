// WEGWERF-REFERENZ der Selbstprüfung (E-149) – KEIN Anwendungscode, kein Vorbild für die Implementierung.
// Deckt nur die Kernfunktionen der kern-Tests ab: Navigation, Kontoansicht mit Liste, Mehrfachauswahl,
// Kontextmenü, Kategorie-Auswahl, Mehrfachbearbeitung (Kategorie), Befehlspalette, mobiles Menü.

const MUTANT = document.documentElement.dataset.mutant || "";
const mut = (n) => MUTANT === n;
const app = document.querySelector('[data-testid="app"]');
const wurzel = document.getElementById("wurzel");

function h(tag, attrs = {}, ...kinder) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") e.textContent = v;
    else if (k.startsWith("on:")) e.addEventListener(k.slice(3), v);
    else e.setAttribute(k, v === true ? "" : String(v));
  }
  for (const k of kinder.flat()) if (k !== null && k !== undefined) e.append(k instanceof Node ? k : String(k));
  return e;
}
const tid = (x, el = document) => el.querySelector(`[data-testid="${x}"]`);

let csrf = null;
async function rest(methode, pfad, body) {
  const kopf = { "Content-Type": "application/json" };
  if (csrf && methode !== "GET") kopf["X-Kontor-CSRF"] = csrf;
  const r = await fetch(pfad, { method: methode, headers: kopf, credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body) });
  if (r.status === 401) { location.href = "/anmelden?weiter=" + encodeURIComponent(location.pathname + location.search).replace(/%2F/g, "/"); throw new Error("401"); }
  const daten = r.status === 204 ? null : await r.json();
  if (!r.ok) { const f = new Error(daten?.fehler?.meldung || "Fehler"); f.daten = daten; throw f; }
  return daten;
}

function meldung(text, art = "erfolg") {
  const m = h("div", { "data-testid": "meldung", "data-art": art, role: art === "fehler" ? "alert" : null, text });
  tid("meldungen").append(m);
  setTimeout(() => m.remove(), 6000);
}

const betrag = (c) => new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(c / 100);
const datum = (iso) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;
function norm(s) {
  let t = s.toLowerCase();
  if (!mut("m8_palette_ohne_umlaute")) t = t.replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss");
  return t.normalize("NFKD").replace(/[̀-ͯ]/g, "");
}
const passt = (eingabe, text) => norm(eingabe).split(/\s+/).filter(Boolean).every((w) => norm(text).includes(w));

// ------------------------------------------------------------------ Grundgerüst
// M28 (oberflaeche.md 37.2): fünf Gruppen; [Ziel, Pfad, Titel, Präfix des data-testid]
const GRUPPEN = [
  ["buchhaltung", "Buchhaltung", [["uebersicht", "/", "Finanzübersicht"], ["konten", "/konten", "Konten"], ["kategorien", "/kategorien", "Kategorien"],
    ["tags", "/tags", "Tags", "navlink-"], ["empfaenger", "/empfaenger", "Empfänger"], ["kredite", "/kredite", "Kredite"]]],
  ["zahlungen", "Zahlungen", [["erwartet", "/erwartet", "Was kommt noch?", "navlink-"], ["mail", "/mail", "Mail-Blatt", "navlink-"]]],
  ["auswertung", "Auswertung", [["berichte", "/berichte", "Berichte"]]],   // M32: ohne Statistik (41.1)
  ["regeln", "Regeln", [["regeln", "/regeln", "Regeln"], ["vorlagen", "/vorlagen", "Split-Vorlagen"], ["dubletten", "/dubletten", "Dubletten"]]],
  ["betrieb", "Betrieb", [["import", "/import", "Import"], ["sync", "/sync", "Synchronisation"], ["protokoll", "/protokoll", "Änderungsprotokoll"],
    ["einstellungen", "/einstellungen", "Einstellungen"], ["konfiguration", "/konfiguration", "Konfiguration", "navlink-"]]]];
const NAV = GRUPPEN.flatMap(([, , l]) => l);
const navId = (z) => (NAV.find((x) => x[0] === z)?.[3] || "nav-") + z;
const ALT = mut("m28_alt_acht") ? ["uebersicht", "konten", "kategorien", "erwartet", "kredite", "berichte", "import", "einstellungen"]
  : ["uebersicht", "konten", "kategorien", "kredite", "berichte", "import", "einstellungen"];
const GEHE = mut("m28_palette_alt") ? ["uebersicht", "konten", "kategorien", "empfaenger", "kredite", "erwartet", "mail", "berichte",
  "tags", "regeln", "vorlagen", "dubletten", "import", "sync", "protokoll", "einstellungen"] : ["uebersicht", "konten", "kategorien", "kredite", "berichte", "import", "einstellungen", "protokoll", "empfaenger",
  "regeln", "vorlagen", "dubletten", "sync", "erwartet", "mail", "tags", "konfiguration"];   // M32 (41.1)

const menueKnopf = h("button", { type: "button", "data-testid": "menue-knopf", "aria-expanded": "false", "aria-controls": "hauptnavigation", "aria-label": "Menü", text: "☰" });
const nav = h("nav", { id: "hauptnavigation", "data-testid": "navigation", "aria-label": "Hauptnavigation" },
  GRUPPEN.map(([g, titel, l]) => h("section", { "aria-labelledby": "nav-g-" + g },
    h("h2", { id: "nav-g-" + g, "data-testid": "nav-gruppe-" + g, text: titel }),
    l.map(([z, p, t]) => h("a", { href: p, "data-testid": navId(z), text: t })))));
// M13 (oberflaeche.md 24.1): der Knopf steht schon in der Hülle und kommt ans Ende der Navigation
if (mut("m13_navigation_erweitert")) nav.append(h("a", { href: "/", "data-testid": "nav-ueber", text: "Über" }));
const versionKnopf = document.querySelector('[data-testid="version-knopf"]') ||
  h("button", { type: "button", "data-testid": "version-knopf", "aria-haspopup": "dialog", text: "Version ?" });
if (mut("m13_knopf_zuerst")) nav.prepend(versionKnopf); else nav.append(versionKnopf);
const hauptbereich = h("main", { "data-testid": "hauptbereich" });
const kopf = h("header", { "data-testid": "app-kopf" }, menueKnopf, h("strong", { text: "Kontor" }),
  h("input", { type: "search", role: "searchbox", "data-testid": "suche-feld", "aria-label": "Suche" }),
  h("button", { type: "button", "data-testid": "befehlspalette-knopf", text: "Befehle", "on:click": () => palette() }),
  h("button", { type: "button", "data-testid": "rueckgaengig-knopf", disabled: true, text: "Rückgängig" }),
  h("button", { type: "button", "data-testid": "wiederholen-knopf", disabled: true, text: "Wiederholen" }));
wurzel.append(kopf, h("div", { class: "rumpf" }, nav, hauptbereich),
  h("div", { "data-testid": "meldungen", role: "status", "aria-live": "polite" }));

const mobilAbfrage = matchMedia("(max-width: 767.98px)");
function layout() { app.dataset.layout = mobilAbfrage.matches ? "mobil" : "desktop"; if (!mobilAbfrage.matches) menueZu(false); }
mobilAbfrage.addEventListener("change", layout);
layout();

let hintergrund = null;
function menueAuf() {
  nav.classList.add("offen"); menueKnopf.setAttribute("aria-expanded", "true");
  hintergrund = h("div", { id: "menue-hintergrund", "data-testid": "menue-hintergrund", "on:click": () => menueZu(true) });
  document.body.append(hintergrund);
  nav.querySelector("a").focus();
}
function menueZu(fokus) {
  if (!nav.classList.contains("offen")) return;
  nav.classList.remove("offen"); menueKnopf.setAttribute("aria-expanded", "false");
  hintergrund?.remove(); hintergrund = null;
  if (fokus) menueKnopf.focus();
}
menueKnopf.addEventListener("click", () => (nav.classList.contains("offen") ? menueZu(true) : menueAuf()));

document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a || a.target || e.defaultPrevented || e.ctrlKey || e.metaKey || e.shiftKey) return;
  const url = new URL(a.href);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  e.preventDefault();
  gehe(url.pathname + url.search);
});
window.addEventListener("popstate", () => zeige());
function gehe(pfad) { history.pushState(null, "", pfad); menueZu(false); zeige(); }

// ------------------------------------------------------------------ Seiten
let daten = { konten: [] };
async function konten() { daten.konten = await rest("GET", "/api/konten"); return daten.konten; }
function pfadVon(k) {
  const nachId = new Map(daten.konten.map((x) => [x.id, x]));
  const teile = []; let x = k;
  while (x) { teile.unshift(x.name); x = x.eltern_id ? nachId.get(x.eltern_id) : null; }
  return teile.join(" › ");
}
function kategorienBaum() {
  const kats = daten.konten.filter((k) => k.art === "aufwand" || k.art === "ertrag");
  const aus = [];
  const gehe = (eltern, art) => kats.filter((k) => k.eltern_id === eltern && k.art === art)
    .sort((a, b) => a.name.localeCompare(b.name, "de")).forEach((k) => { aus.push(k); gehe(k.id, art); });
  gehe(null, "aufwand"); gehe(null, "ertrag");
  return aus;
}

function seite(name, titel, ...inhalt) {
  document.title = `${titel} – Kontor`;
  const s = h("section", { "data-testid": "seite-" + name, "data-geladen": "nein" }, h("h1", { text: titel }), ...inhalt);
  hauptbereich.replaceChildren(s);
  return s;
}

async function zeige() {
  schliesseEbenen();
  const pfad = location.pathname;
  for (const a of nav.querySelectorAll("a")) a.removeAttribute("aria-current");
  const aktiv = NAV.find(([, p]) => (p === "/" ? pfad === "/" : pfad === p || pfad.startsWith(p + "/")));
  if (aktiv) tid(navId(aktiv[0])).setAttribute("aria-current", "page");
  let s;
  const m = pfad.match(/^\/konten\/(\d+)$/);
  try {
    await konten();
    if (m) s = await kontoansicht(Number(m[1]));
    else if (pfad === "/") s = await uebersicht();
    else if (pfad === "/empfaenger") s = await empfaengerSeite();
    else if (pfad === "/sync") s = await syncSeite();
    else if (aktiv) s = seite(aktiv[0], aktiv[2]);
    else if (pfad === "/benachrichtigungen") s = seite("benachrichtigungen", "Benachrichtigungen");
    else s = seite("nicht-gefunden", "Nicht gefunden");
  } catch (e) { s = seite("nicht-gefunden", "Nicht gefunden"); }
  s.dataset.geladen = "ja";
  app.dataset.bereit = "ja";
}

// ------------------------------------------------------------------ Finanzübersicht (6, M11 22.1)
function speicher(schluessel, wert) {
  try { if (wert === undefined) return localStorage.getItem(schluessel); localStorage.setItem(schluessel, wert); } catch (e) { return null; }
  return null;
}
async function uebersicht() {
  const u = await rest("GET", "/api/kontenuebersicht");
  const nachId = new Map(u.konten.map((k) => [k.konto_id, k]));
  const geschlossene = h("input", { type: "checkbox", "data-testid": "uebersicht-geschlossene", id: "u-geschl" });
  const baum = (arten, testid) => {
    const aus = [];
    const geh = (eltern, tiefe) => u.konten.filter((k) => k.eltern_id === eltern && arten.includes(k.art))
      .sort((a, b) => a.name.localeCompare(b.name, "de")).forEach((k) => { aus.push([k, tiefe]); geh(k.konto_id, tiefe + 1); });
    geh(null, 1);
    return aus.map(([k, tiefe]) => {
      const anzeige = k.art === "ertrag" || k.art === "eigenkapital" ? -k.saldo_gesamt : k.saldo_gesamt;
      const z = h("div", { role: "row", tabindex: "0", "data-testid": testid + k.konto_id, "aria-level": tiefe, "data-geschlossen": k.geschlossen ? "ja" : "nein", "data-art": k.art },
        h("span", { "data-feld": "name", text: k.name }), " ",
        h("span", { "data-feld": "saldo", "data-betrag": k.saldo_gesamt, text: betrag(anzeige) }));
      z.addEventListener("click", () => gehe("/konten/" + k.konto_id));
      z.addEventListener("keydown", (e) => { if (e.key === "Enter") gehe("/konten/" + k.konto_id); });
      return z;
    });
  };
  const tabelle = h("div", { role: "table", "data-testid": "uebersicht-tabelle" }, baum(BESTAND, "uebersicht-konto-"));
  const summe = h("div", { "data-testid": "uebersicht-summe", "data-betrag": u.summe_bestand, text: betrag(u.summe_bestand) });
  const SCHL = "kontor.uebersicht.kategorien";
  let offen = speicher(SCHL) === "auf";
  if (mut("m11_kategorien_anfangs_offen") && speicher(SCHL) === null) offen = true;
  const inhalt = h("div", { id: "uebersicht-kategorien-inhalt" });
  const gruppen = [["aufwand", "Ausgaben"], ["ertrag", "Einnahmen"], ["eigenkapital", "Sonstige"]]
    .filter(([art]) => u.konten.some((k) => k.art === art))
    .map(([art, titel]) => {
      const s = u.konten.filter((k) => k.art === art).reduce((a, k) => a + k.saldo, 0);
      return h("div", { role: "group", "data-testid": "uebersicht-gruppe-" + art, "aria-label": titel }, h("h3", { text: titel }),
        baum([art], "uebersicht-kategorie-"),
        h("div", { "data-testid": "uebersicht-summe-" + art, "data-betrag": s, text: betrag(art === "aufwand" ? s : -s) }));
    });
  inhalt.append(...gruppen);
  const knopf = h("button", { type: "button", "data-testid": "uebersicht-kategorien-umschalten", "aria-controls": "uebersicht-kategorien-inhalt", text: "Kategorien" });
  const setze = () => { knopf.setAttribute("aria-expanded", offen ? "true" : "false"); inhalt.hidden = !offen; };
  knopf.addEventListener("click", () => { offen = !offen; speicher(SCHL, offen ? "auf" : "zu"); setze(); });
  setze();
  const bereich = h("section", { "data-testid": "uebersicht-kategorien", class: "abgesetzt" }, h("h2", {}, knopf), inhalt);
  const filtern = () => {
    for (const z of document.querySelectorAll('[data-testid^="uebersicht-konto-"],[data-testid^="uebersicht-kategorie-"]'))
      z.hidden = z.dataset.geschlossen === "ja" && !geschlossene.checked;
  };
  geschlossene.addEventListener("change", filtern);
  const s = seite("uebersicht", "Finanzübersicht", h("label", {}, geschlossene, " Geschlossene anzeigen"), tabelle, summe, bereich);
  filtern();
  void nachId;
  return s;
}

// ------------------------------------------------------------------ Empfänger (13.10, M11 22.3)
async function empfaengerSeite() {
  const liste_ = await rest("GET", "/api/empfaenger");
  const knopf = h("button", { type: "button", "data-testid": "empfaenger-zusammenfuehren", text: "Zusammenführen…", disabled: true });
  const gewaehlt = new Set();
  const zeilen = liste_.map((e) => {
    const box = h("input", { type: "checkbox", "data-testid": "empfaenger-auswahl-" + e.id, "aria-label": e.name });
    box.addEventListener("change", () => { box.checked ? gewaehlt.add(e.id) : gewaehlt.delete(e.id); knopf.disabled = gewaehlt.size < 2; });
    return h("div", { role: "row", "data-testid": "empfaenger-" + e.id }, box, " ", h("span", { text: e.name }), " ",
      h("span", { class: "aliase", text: e.aliase.join(", ") }));
  });
  knopf.addEventListener("click", () => zusammenfuehrenDialog(knopf, liste_.filter((e) => gewaehlt.has(e.id))));
  return seite("empfaenger", "Empfänger", knopf, h("div", { role: "table" }, zeilen));
}
async function zusammenfuehrenDialog(ausloeser, auswahl) {
  const anzahl = new Map();
  for (const e of auswahl) anzahl.set(e.id, (await rest("GET", `/api/buchungen?empfaenger_id=${e.id}&pro_seite=1`)).gesamt);
  const vorgabe = [...auswahl].sort((a, b) => (anzahl.get(b.id) - anzahl.get(a.id)) || (a.id - b.id))[0];
  const ziel = h("select", { "data-testid": "zusammenfuehren-ziel", "aria-label": "Ziel" }, auswahl.map((e) => h("option", { value: e.id, text: e.name })));
  ziel.value = String(vorgabe.id);
  const name = h("input", { type: "text", "data-testid": "zusammenfuehren-name", "aria-label": "Name", value: vorgabe.name });
  const vorschau = h("div", { "data-testid": "zusammenfuehren-aliase" });
  const fehler = h("div", { role: "alert", hidden: true });
  const zeigeVorschau = () => {
    const z = auswahl.find((e) => String(e.id) === ziel.value);
    const namen = [...z.aliase, ...(name.value.trim() !== z.name ? [z.name] : []), ...auswahl.filter((e) => e !== z).flatMap((e) => [e.name, ...e.aliase])];
    vorschau.textContent = "Suchtexte: " + [...new Set(namen)].join(", ");
  };
  ziel.addEventListener("change", () => { name.value = auswahl.find((e) => String(e.id) === ziel.value).name; zeigeVorschau(); });
  name.addEventListener("input", zeigeVorschau);
  zeigeVorschau();
  const los = h("button", { type: "button", "data-testid": "zusammenfuehren-ausfuehren", text: "Zusammenführen" });
  los.addEventListener("click", async () => {
    const z = auswahl.find((e) => String(e.id) === ziel.value);
    const body = { quelle_ids: auswahl.filter((e) => e !== z).map((e) => e.id) };
    if (name.value.trim() !== z.name && !mut("m11_zusammenfuehren_ohne_name")) body.name = name.value;
    try {
      await rest("POST", `/api/empfaenger/${z.id}/zusammenfuehren`, body);
      schliesseDialog(false); meldung("Empfänger zusammengeführt"); await zeige();
    } catch (e) { fehler.hidden = false; fehler.textContent = e.message; }
  });
  oeffneDialog("zusammenfuehren-dialog", "Empfänger zusammenführen", [ziel, name, vorschau, fehler, los], ausloeser);
}

// ------------------------------------------------------------------ Synchronisation (13.10, M11 22.4)
async function syncSeite() {
  const zustand = await rest("GET", "/api/sync/konten");
  const laeufe = await rest("GET", "/api/sync/laeufe");
  const zeilen = zustand.map((z) => {
    let letzter = null;
    for (const l of [...laeufe].sort((a, b) => a.id - b.id))
      for (const k of l.konten) if (k.iban === z.iban && k.status === "erfolgreich" && k.saldo_abgleich) letzter = k;
    const sa = letzter ? letzter.saldo_abgleich : null;
    const saldo = h("span", { "data-testid": "bankkonto-saldo", "data-status": sa ? sa.status : "" },
      sa && sa.bank_saldo !== null ? `Bank ${betrag(sa.bank_saldo)} am ${datum(sa.stichtag)}, Differenz ${betrag(sa.differenz)}` : "");
    const link = sa && sa.status === "ausgeglichen" ? h("a", { href: "/konten/" + letzter.konto_id, "data-testid": "bankkonto-ausgleich-" + z.iban, text: "Ausgleichsbuchung" }) : null;
    return h("div", { "data-testid": "bankkonto-" + z.iban }, h("span", { text: z.iban }), " ", saldo, " ", link);
  });
  return seite("sync", "Synchronisation", h("div", { "data-testid": "sync-status" }), zeilen);
}

// ------------------------------------------------------------------ Kontoansicht
const BESTAND = ["girokonto", "sparkonto", "kreditkonto"];
const klasseVon = (k) => (BESTAND.includes(k.art) ? "bestand" : k.art);
let liste = null; // {konto, zeilen: [ids], buchungen: Map, auswahl: Set, anker, fokus}
async function kontoansicht(id) {
  const konto = daten.konten.find((k) => k.id === id);
  if (!konto) return seite("nicht-gefunden", "Nicht gefunden");
  const klasse = klasseVon(konto);
  const q = new URLSearchParams(location.search);
  const grid = h("div", { role: "grid", "data-testid": "buchungsliste", "aria-multiselectable": "true", "data-kompakt": app.dataset.layout === "mobil" ? "ja" : "nein" });
  const anzahl = h("span", { "data-testid": "buchungsliste-anzahl" });
  const summe = h("span", { "data-testid": "buchungsliste-summe" });
  const auswahlAnzahl = h("span", { "data-testid": "auswahl-anzahl", "data-anzahl": "0", text: "0 ausgewählt" });
  const leiste = h("div", { class: "leiste", "data-testid": "mehrfach-leiste", hidden: true },
    auswahlAnzahl,
    h("button", { type: "button", "data-testid": "mehrfach-kategorie", text: "Kategorie setzen", "on:click": (e) => kategorieWaehlen(e.currentTarget, [...liste.auswahl]) }),
    h("button", { type: "button", "data-testid": "mehrfach-status", text: "Status setzen", "on:click": (e) => statusWaehlen(e.currentTarget, [...liste.auswahl]) }),
    h("button", { type: "button", "data-testid": "auswahl-aufheben", text: "Auswahl aufheben", "on:click": () => setzeAuswahl(new Set()) }));
  // M11 (oberflaeche.md 22.2): Unterkonten in jeder Kontoansicht, Konto-Filter in Nicht-Bestandskonten
  const unter = h("input", { type: "checkbox", id: "f-unterkonten", "data-testid": "filter-unterkonten" });
  unter.checked = q.get("unterkonten") === "true";
  const filter = [h("label", {}, unter, " Unterkonten einschließen")];
  let kontoFilter = null;
  if (klasse !== "bestand") {
    kontoFilter = h("select", { "data-testid": "filter-konto", "aria-label": "Konto" }, h("option", { value: "", text: "alle Konten" }),
      daten.konten.filter((k) => BESTAND.includes(k.art)).map((k) => h("option", { value: k.id, text: pfadVon(k) })));
    kontoFilter.value = q.get("kategorie_id") || "";
    filter.push(kontoFilter);
  }
  // M12 (oberflaeche.md 23.1): Filterleiste anfangs eingeklappt, Zahl der Filter am Umschalter
  const filterAnzahl = h("span", { "data-testid": "filter-anzahl" });
  const umschalten = h("button", { type: "button", "data-testid": "filter-baukasten-umschalten", "aria-controls": "filter-leiste", text: "Filter " }, filterAnzahl);
  const filterLeiste = h("div", { id: "filter-leiste", "data-testid": "filter-leiste" }, filter);
  const offen = mut("m12_filter_offen") && app.dataset.layout !== "mobil";
  filterLeiste.hidden = !offen; umschalten.setAttribute("aria-expanded", offen ? "true" : "false");
  umschalten.addEventListener("click", () => { filterLeiste.hidden = !filterLeiste.hidden; umschalten.setAttribute("aria-expanded", filterLeiste.hidden ? "false" : "true"); });
  const zaehle = () => { const n = [...new URLSearchParams(location.search).keys()].length; filterAnzahl.dataset.anzahl = n; filterAnzahl.textContent = n ? `(${n})` : ""; };
  zaehle();
  const panel = h("aside", { "data-testid": "panel-details", "aria-label": "Einzelheiten" });
  const s = seite("konto", konto.name, umschalten, filterLeiste, anzahl, summe, grid, leiste, panel);
  s.dataset.kontoklasse = klasse;
  liste = { konto, klasse, grid, leiste, anzahl, summe, unter, kontoFilter, zeilen: [], buchungen: new Map(), auswahl: new Set(), anker: null, fokus: null,
    von: q.get("von"), bis: q.get("bis"), seiten: 1, gesamt: 0 };
  const wechsel = async () => {
    const p = new URLSearchParams();
    if (unter.checked) p.set("unterkonten", "true");
    if (kontoFilter && kontoFilter.value) p.set("kategorie_id", kontoFilter.value);
    history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : ""));
    zaehle();
    s.dataset.geladen = "nein"; setzeAuswahl(new Set()); await neuLaden(); s.dataset.geladen = "ja";
  };
  unter.addEventListener("change", wechsel);
  kontoFilter?.addEventListener("change", wechsel);
  await neuLaden();
  await sprungziel(q);
  grid.addEventListener("click", listeKlick);
  grid.addEventListener("contextmenu", listeKontext);
  grid.addEventListener("keydown", listeTaste);
  return s;
}
function listenAbfrage() {
  const p = new URLSearchParams({ konto_id: liste.konto.id, sortierung: "-datum", pro_seite: 200 });
  if (liste.unter.checked && !mut("m11_unterkonten_ignoriert")) p.set("unterkonten", "true");
  if (liste.kontoFilter && liste.kontoFilter.value) p.set("kategorie_id", liste.kontoFilter.value);
  if (liste.von) p.set("von", liste.von);
  if (liste.bis) p.set("bis", liste.bis);
  return "/api/buchungen?" + p;
}
function zeileBauen(b) {
  const kat = daten.konten.find((k) => k.id === b.kategorie_id);
  const zellen = [
    h("div", { role: "gridcell", "data-feld": "datum", "data-datum": b.datum, text: datum(b.datum) }),
    h("div", { role: "gridcell", "data-feld": "empfaenger", "data-empfaenger-id": b.empfaenger ? b.empfaenger.id : "", text: b.empfaenger ? b.empfaenger.name : "" }),
    h("div", { role: "gridcell", "data-feld": "verwendungszweck", text: b.verwendungszweck }),
    h("div", { role: "gridcell", "data-feld": "kategorie", "data-kategorie-id": b.kategorie_id ?? "", text: kat ? pfadVon(kat) : kategorieText(b) })];
  if (liste && liste.klasse !== "bestand") {
    const bestand = [...new Set(b.splits.map((x) => x.konto_id))].map((i) => daten.konten.find((k) => k.id === i)).filter((k) => k && BESTAND.includes(k.art));
    const eins = bestand.length === 1 || (mut("m11_konto_erstes") && bestand.length > 1);
    zellen.push(h("div", { role: "gridcell", "data-feld": "konto", "data-konto-id": eins ? bestand[0].id : "", text: eins ? pfadVon(bestand[0]) : bestand.length ? "Mehrere" : "" }));
  }
  zellen.push(h("div", { role: "gridcell", "data-feld": "status", text: STATUS_TEXT[b.status] }));
  zellen.push(h("div", { role: "gridcell", "data-feld": "betrag", "data-betrag": b.betrag, text: betrag(b.betrag) }));
  return h("div", { role: "row", "data-testid": "buchung-" + b.id, "aria-selected": "false", tabindex: "-1", "data-status": b.status, "data-vorschlag": b.vorschlag ? "ja" : "nein" }, zellen);
}
function kategorieText(b) {
  const gegen = b.splits.map((s) => daten.konten.find((k) => k.id === s.konto_id)).filter((k) => k && !BESTAND.includes(k.art));
  return gegen.length > 1 ? "Gesplittet" : gegen.length === 0 ? "Umbuchung" : pfadVon(gegen[0]);
}
async function neuLaden() {
  const d = await rest("GET", listenAbfrage());
  for (let n = 2; n <= liste.seiten && d.eintraege.length < d.gesamt; n++) {
    const w = await rest("GET", listenAbfrage() + "&seite=" + n);
    d.eintraege.push(...w.eintraege);
  }
  liste.gesamt = d.gesamt;
  liste.anzahl.dataset.anzahl = d.gesamt; liste.anzahl.textContent = `${d.gesamt} Buchungen`;
  liste.summe.dataset.betrag = d.summe; liste.summe.textContent = betrag(d.summe);
  liste.zeilen = d.eintraege.map((b) => b.id);
  liste.buchungen = new Map(d.eintraege.map((b) => [b.id, b]));
  const kopf = ["Datum", "Empfänger", "Verwendungszweck", "Kategorie", ...(liste.klasse !== "bestand" ? ["Konto"] : []), "Status", "Betrag"];
  liste.grid.replaceChildren(h("div", { role: "row" }, kopf.map((t) => h("div", { role: "columnheader", text: t }))));
  for (const b of d.eintraege) {
    const z = zeileBauen(b);
    z.setAttribute("aria-selected", liste.auswahl.has(b.id) ? "true" : "false");
    liste.grid.append(z);
  }
  liste.auswahl = new Set([...liste.auswahl].filter((i) => liste.buchungen.has(i)));
  const fokus = liste.zeilen.includes(liste.fokus) ? liste.fokus : liste.zeilen[0];
  if (fokus !== undefined) setzeFokus(fokus, false);
  setzeAuswahl(liste.auswahl);
}
const zeileVon = (el) => el?.closest('[role="row"][data-testid^="buchung-"]');
const idVon = (z) => Number(z.dataset.testid.slice(8));
function bereich(a, b) {
  const i = liste.zeilen.indexOf(a), j = liste.zeilen.indexOf(b);
  return liste.zeilen.slice(Math.min(i, j), Math.max(i, j) + 1);
}
function setzeAuswahl(menge) {
  liste.auswahl = menge;
  if (!tid("auswahl-anzahl")) return;
  for (const id of liste.zeilen) tid("buchung-" + id, liste.grid).setAttribute("aria-selected", menge.has(id) ? "true" : "false");
  const z = tid("auswahl-anzahl"); z.dataset.anzahl = menge.size; z.textContent = `${menge.size} ausgewählt`;
  liste.leiste.hidden = menge.size === 0;
  details(menge);
}
// M28 (oberflaeche.md 37.8): Einzelheiten mit Stiften; hier nur der Status (Kern-Tests von M12)
function details(menge) {
  const p = tid("panel-details");
  if (!p || mut("m28_stift_ohne_status")) return;
  const id = menge.size === 1 ? [...menge][0] : null;
  if (id === null) { p.replaceChildren(); return; }
  const b = liste.buchungen.get(id);
  const zeileStatus = h("div", { "data-feld": "status" }, h("span", { text: STATUS_TEXT[b.status] }));
  const stift = h("button", { type: "button", "data-testid": "stift-status", "aria-label": "Status bearbeiten", text: "✎" });
  stift.addEventListener("click", () => {
    const ed = h("select", { "data-testid": "inline-editor", "data-feld": "status", "aria-label": "Status" },
      STATUS.map((x) => h("option", { value: x, text: STATUS_TEXT[x] })));
    ed.value = b.status;
    zeileStatus.replaceChildren(ed);
    ed.addEventListener("keydown", (ev) => { ev.stopPropagation(); if (ev.key === "Escape") { ev.preventDefault(); details(liste.auswahl); } });
    ed.addEventListener("change", () => statusSetzen(stift, [id], ed.value));
    ed.focus();
  });
  p.replaceChildren(h("h2", { text: "Einzelheiten" }), zeileStatus, stift);
}
function setzeFokus(id, fokussieren = true) {
  for (const x of liste.zeilen) tid("buchung-" + x, liste.grid).tabIndex = x === id ? 0 : -1;
  liste.fokus = id;
  if (fokussieren) tid("buchung-" + id, liste.grid).focus();
}
function auswahlKlick(id, strgTaste, umschalt) {
  if (mut("m8_strg_ersetzt")) strgTaste = false;
  let anker = liste.anker;
  if (mut("m8_umschalt_ohne_anker") && umschalt) anker = liste.zeilen[0];
  if (umschalt && anker !== null) {
    const b = new Set(bereich(anker, id));
    setzeAuswahl(strgTaste ? new Set([...liste.auswahl, ...b]) : b);
  } else if (strgTaste) {
    const m = new Set(liste.auswahl); m.has(id) ? m.delete(id) : m.add(id); setzeAuswahl(m); liste.anker = id;
  } else { setzeAuswahl(new Set([id])); liste.anker = id; }
  setzeFokus(id);
}
function listeKlick(e) {
  const z = zeileVon(e.target); if (!z) return;
  auswahlKlick(idVon(z), e.ctrlKey || e.metaKey, e.shiftKey);
}
function listeTaste(e) {
  if (!liste.zeilen.length || e.target.closest("input,select,textarea")) return;
  const i = liste.zeilen.indexOf(liste.fokus);
  let ziel = null;
  if (e.key === "ArrowDown") ziel = liste.zeilen[Math.min(i + 1, liste.zeilen.length - 1)];
  else if (e.key === "ArrowUp") ziel = liste.zeilen[Math.max(i - 1, 0)];
  else if (e.key === "Home") ziel = liste.zeilen[0];
  else if (e.key === "End") ziel = liste.zeilen[liste.zeilen.length - 1];
  if (ziel !== null) {
    e.preventDefault();
    if (e.shiftKey && liste.anker !== null) setzeAuswahl(new Set(bereich(liste.anker, ziel)));
    else if (!(e.ctrlKey || e.metaKey)) { setzeAuswahl(new Set([ziel])); liste.anker = ziel; }
    setzeFokus(ziel); return;
  }
  if (e.key === " ") { e.preventDefault(); const m = new Set(liste.auswahl); m.has(liste.fokus) ? m.delete(liste.fokus) : m.add(liste.fokus); setzeAuswahl(m); liste.anker = liste.fokus; }
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") { e.preventDefault(); setzeAuswahl(new Set(liste.zeilen)); }
  else if ((e.shiftKey && e.key === "F10") || e.key === "ContextMenu") {
    e.preventDefault(); const z = tid("buchung-" + liste.fokus, liste.grid); const r = z.getBoundingClientRect();
    kontextmenue(z, r.left + 20, r.bottom, e.altKey);
  }
}

// ------------------------------------------------------------------ Kontextmenü
let menue = null;
function listeKontext(e) {
  const z = zeileVon(e.target); if (!z) return;
  e.preventDefault();
  const id = idVon(z);
  if (!liste.auswahl.has(id) && !mut("m8_kontextmenue_ohne_auswahl")) { setzeAuswahl(new Set([id])); liste.anker = id; }
  setzeFokus(id);
  kontextmenue(z, e.clientX, e.clientY, e.altKey);
}
function kontextmenue(ausloeser, x, y, alt = false) {
  schliesseMenue(false);
  const n = liste.auswahl.size;
  const eintraege = [["km-kategorie", "Kategorie setzen…", true, (el) => kategorieWaehlen(ausloeser, [...liste.auswahl])],
    ["km-tags", "Tags…", true, null], ["km-splitten", "Splitten…", n === 1, null], ["km-dublette", "Als Dublette markieren…", false, null],
    ["km-vorschlag-annehmen", "Vorschlag annehmen", false, null], ["km-vorschlag-ablehnen", "Vorschlag ablehnen", false, null],
    ["km-bearbeiten", "Verwendungszweck bearbeiten", n === 1, null],
    ["km-status", "Status setzen…", true, () => statusWaehlen(ausloeser, [...liste.auswahl])], ["km-mehrfach", "Bearbeiten…", true, null],
    ["km-loeschen", "Löschen…", true, null]];
  // M28 (oberflaeche.md 37.4): kein Eintrag „Warum wiederkehrend?“ mehr (auch nicht mit Alt)
  zeigeMenue(ausloeser, x, y, eintraege);
}
function zeigeMenue(ausloeser, x, y, eintraege) {
  schliesseMenue(false);
  const m = h("div", { role: "menu", "data-testid": "kontextmenue", "aria-label": "Aktionen" },
    eintraege.map(([t, text, aktiv, tat]) => h("div", { role: "menuitem", tabindex: "-1", "data-testid": t, "aria-disabled": aktiv ? null : "true", text,
      "on:click": () => { if (!aktiv) return; schliesseMenue(false); tat && tat(); } })));
  document.body.append(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.max(0, Math.min(x, innerWidth - r.width - 2)) + "px";
  m.style.top = Math.max(0, Math.min(y, innerHeight - r.height - 2)) + "px";
  menue = { el: m, ausloeser };
  const aktive = () => [...m.querySelectorAll('[role="menuitem"]:not([aria-disabled="true"])')];
  aktive()[0].focus();
  m.addEventListener("keydown", (e) => {
    const a = aktive(); const i = a.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); a[(i + 1) % a.length].focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); a[(i - 1 + a.length) % a.length].focus(); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); document.activeElement.click(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); schliesseMenue(true); }
  });
}
function schliesseMenue(fokus) {
  if (!menue) return;
  const { el, ausloeser } = menue; menue = null; el.remove();
  if (fokus && !mut("m8_esc_ohne_fokus")) ausloeser.focus();
}
document.addEventListener("mousedown", (e) => { if (menue && !menue.el.contains(e.target)) schliesseMenue(false); }, true);

// ------------------------------------------------------------------ Dialoge
let dialog = null;
function oeffneDialog(testid, titel, inhalt, ausloeser) {
  schliesseDialog(false);
  const kennung = "dlg-" + testid;
  const d = h("div", { role: "dialog", "aria-modal": "true", "aria-labelledby": kennung, "data-testid": testid },
    h("h2", { id: kennung, text: titel }), inhalt);
  document.body.append(d);
  dialog = { el: d, ausloeser };
  d.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); schliesseDialog(true); } });
  return d;
}
function schliesseDialog(fokus) {
  if (!dialog) return;
  const { el, ausloeser } = dialog; dialog = null; el.remove();
  if (fokus && ausloeser && document.contains(ausloeser)) ausloeser.focus();
}
// ------------------------------------------------------------------ About-Fenster (M13, oberflaeche.md 24)
let ueberVorrat = null;
async function ueberOeffnen() {
  const mobil = app.dataset.layout === "mobil";
  let a;
  try {
    a = mut("m13_ohne_neuladen") && ueberVorrat ? ueberVorrat : await rest("GET", "/api/version");
  } catch (e) { if (e.message !== "401") meldung(e.message || "Fehler", "fehler"); return; }
  menueZu(false);
  const ausloeser = mobil && !mut("m13_fokus_mobil_falsch") ? menueKnopf : versionKnopf;
  const zeile = (tid_, text) => h("p", { "data-testid": tid_, text });
  const schliessen = h("button", { type: "button", "data-testid": "ueber-schliessen", text: "Schließen",
    "on:click": () => schliesseDialog(true) });
  const x = h("button", { type: "button", "data-testid": "ueber-x", "aria-label": "Schließen", text: "×",
    "on:click": () => schliesseDialog(true) });
  const d = oeffneDialog("ueber-dialog", "Über Kontor", [x,
    zeile("ueber-version", "Version " + a.version),
    zeile("ueber-build", a.entwicklungsstand ? "Entwicklungsstand (nicht über die Release-CI gebaut)"
      : `Build ${a.build_datum} · Commit ${a.commit}`),
    zeile("ueber-modus", a.modus === "mock" ? "Mock-Modus" : "Echtbetrieb"),
    zeile("ueber-python", "Python " + a.python),
    zeile("ueber-datenbank", a.datenbank),
    zeile("ueber-schema", `Datenbank ${a.datenbank_schema} · Sicherung ${a.sicherung_schema}`),
    h("p", {}, h("a", { href: a.repository, target: "_blank", rel: "noopener noreferrer",
      "data-testid": "ueber-repository", text: "Quellcode" })),
    schliessen], ausloeser);
  d.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...d.querySelectorAll("button, a[href]")];
    const i = f.indexOf(document.activeElement);
    e.preventDefault();
    f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
  });
  schliessen.focus();
}
versionKnopf.addEventListener("click", () => ueberOeffnen());

function kategorieWaehlen(ausloeser, ids) {
  const kats = kategorienBaum();
  const suche = h("input", { type: "text", "data-testid": "kategorie-auswahl-suche", "aria-label": "Kategorie suchen" });
  const lb = h("div", { role: "listbox", "data-testid": "kategorie-auswahl-liste", "aria-label": "Kategorien" });
  let markiert = -1;
  const sichtbar = () => [...lb.querySelectorAll('[role="option"]')];
  const fuellen = () => {
    lb.replaceChildren(...kats.filter((k) => passt(suche.value, pfadVon(k))).map((k) =>
      h("div", { role: "option", "data-testid": "kategorie-option-" + k.id, "aria-selected": "false", text: pfadVon(k), "on:click": () => waehle(k.id) })));
    markiert = -1;
  };
  const markiere = (i) => { const o = sichtbar(); if (!o.length) return; markiert = (i + o.length) % o.length; o.forEach((x, j) => x.setAttribute("aria-selected", j === markiert ? "true" : "false")); };
  async function waehle(kid) {
    schliesseDialog(true);
    let auswahl = [...ids].sort((a, b) => a - b);
    try {
      if (auswahl.length === 1) await rest("PUT", `/api/buchungen/${auswahl[0]}/kategorie`, { kategorie_id: kid });
      else {
        if (mut("m8_mehrfach_nur_erste")) auswahl = auswahl.slice(0, 1);
        await rest("POST", "/api/buchungen/mehrfach/kategorie", { buchung_ids: auswahl, kategorie_id: kid });
      }
      meldung("Kategorie gesetzt");
    } catch (e) { meldung(mut("m8_fehler_ohne_servermeldung") ? "Fehler" : e.message, "fehler"); }
    await neuLaden();
  }
  suche.addEventListener("input", fuellen);
  suche.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); markiere(markiert + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); markiere(markiert - 1); }
    else if (e.key === "Enter") { e.preventDefault(); const o = sichtbar()[Math.max(markiert, 0)]; if (o) o.click(); }
  });
  fuellen();
  oeffneDialog("kategorie-auswahl", "Kategorie wählen", [suche, lb], ausloeser);
  suche.focus();
}

// ------------------------------------------------------------------ M12: Status (oberflaeche.md 23.2 bis 23.4)
const STATUS = ["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"];
const STATUS_TEXT = { importiert: "Importiert", vorlaeufig: "Vorläufig", bestaetigt: "Bestätigt", abgeglichen: "Abgeglichen" };
function listeDoppelklick(e) {
  const zelle = e.target.closest('[data-feld="status"]'); const z = zeileVon(e.target);
  if (!zelle || !z || zelle.querySelector('[data-testid="inline-editor"]')) return;
  const id = idVon(z); const alt = liste.buchungen.get(id).status;
  const ed = h("select", { "data-testid": "inline-editor", "data-feld": "status", "aria-label": "Status" },
    STATUS.map((x) => h("option", { value: x, text: STATUS_TEXT[x] })));
  ed.value = alt;
  zelle.replaceChildren(ed);
  let fertig = false;
  const ende = () => { if (!fertig) { fertig = true; zelle.textContent = STATUS_TEXT[alt]; } };
  ed.addEventListener("keydown", (ev) => { ev.stopPropagation(); if (ev.key === "Escape") { ev.preventDefault(); ende(); } });
  ed.addEventListener("change", () => { fertig = true; statusSetzen(zelle, [id], ed.value); });
  ed.addEventListener("click", (ev) => ev.stopPropagation());
  ed.focus();
}
function statusWaehlen(ausloeser, ids) {
  const knoepfe = STATUS.map((x) => h("button", { type: "button", "data-testid": "status-waehlen-" + x, text: STATUS_TEXT[x],
    "on:click": () => { schliesseDialog(true); statusSetzen(ausloeser, ids, x); } }));
  oeffneDialog("status-auswahl", "Status setzen", knoepfe, ausloeser);
  knoepfe[0].focus();
}
async function statusSetzen(ausloeser, ids, status) {
  let auswahl = [...ids].sort((a, b) => a - b);
  if (mut("m12_mehrfach_status_nur_erste")) auswahl = auswahl.slice(0, 1);
  const abgeglichen = auswahl.filter((i) => liste.buchungen.get(i)?.status === "abgeglichen" && status !== "abgeglichen");
  const senden = async (entsperren) => {
    try {
      if (mut("m12_status_per_patch") && auswahl.length === 1) await rest("PATCH", `/api/buchungen/${auswahl[0]}`, { status });
      else await rest("POST", "/api/buchungen/mehrfach/aendern", { buchung_ids: auswahl, status, ...(entsperren ? { entsperren: true } : {}) });
      meldung("Status gesetzt");
    } catch (e) { meldung(e.message, "fehler"); }
    await neuLaden();
  };
  if (abgeglichen.length && !mut("m12_ohne_rueckfrage")) {
    const nein = h("button", { type: "button", "data-testid": "bestaetigen-nein", text: "Abbrechen", "on:click": async () => { schliesseDialog(false); await neuLaden(); } });
    const ja = h("button", { type: "button", "data-testid": "bestaetigen-ja", text: "Entsperren", "on:click": () => { schliesseDialog(false); senden(true); } });
    oeffneDialog("bestaetigen-dialog", `${abgeglichen.length} abgeglichene Buchung(en) entsperren?`, [ja, nein], ausloeser);
    nein.focus();
    return;
  }
  await senden(abgeglichen.length > 0);
}

// ------------------------------------------------------------------ Befehlspalette
let paletteOffen = null;
function befehle() {
  const feste = GEHE.map((z) => NAV.find((x) => x[0] === z)).map(([z, p, t]) => ["gehe-" + z, "Gehe zu: " + t, () => gehe(p)]);
  feste.push(["gehe-benachrichtigungen", "Gehe zu: Benachrichtigungen", () => gehe("/benachrichtigungen")],
    ["rueckgaengig", "Rückgängig", () => {}], ["wiederholen", "Wiederholen", () => {}],
    ["synchronisieren", "Bankkonten jetzt synchronisieren", () => {}], ["thema-system", "Design: wie System", () => {}],
    ["thema-hell", "Design: Hell", () => {}], ["thema-dunkel", "Design: Dunkel", () => {}], ["layout-zuruecksetzen", "Layout zurücksetzen", () => {}]);
  const kontenB = daten.konten.filter((k) => ["girokonto", "sparkonto", "kreditkonto"].includes(k.art) && !k.geschlossen)
    .sort((a, b) => a.name.localeCompare(b.name, "de")).map((k) => ["konto-" + k.id, "Konto öffnen: " + k.name, () => gehe("/konten/" + k.id)]);
  return [...feste, ...kontenB];
}
function palette() {
  if (paletteOffen) return;
  const vorher = document.activeElement;
  const eingabe = h("input", { type: "text", role: "combobox", "data-testid": "befehlspalette-eingabe", "aria-expanded": "true", "aria-controls": "befehlsliste", "aria-label": "Befehl" });
  const lb = h("div", { role: "listbox", id: "befehlsliste", "data-testid": "befehlspalette-liste", "aria-label": "Befehle" });
  const alle = befehle();
  let treffer = [], aktiv = 0;
  const fuellen = () => {
    treffer = alle.filter(([, t]) => passt(eingabe.value, t)); aktiv = 0; zeichnen();
  };
  const zeichnen = () => {
    lb.replaceChildren(...treffer.map(([id, t, tat], i) => h("div", { role: "option", id: "befehl-opt-" + id, "data-testid": "befehl-" + id, "aria-selected": i === aktiv ? "true" : "false", text: t, "on:click": () => ausfuehren(i) })));
    if (treffer.length) eingabe.setAttribute("aria-activedescendant", "befehl-opt-" + treffer[aktiv][0]); else eingabe.removeAttribute("aria-activedescendant");
  };
  const zu = (fokus) => { d.remove(); paletteOffen = null; if (fokus && vorher && document.contains(vorher)) vorher.focus(); };
  const ausfuehren = (i) => { const b = treffer[i]; zu(false); if (b) b[2](); };
  eingabe.addEventListener("input", fuellen);
  const d = h("div", { role: "dialog", "aria-modal": "true", "aria-label": "Befehlspalette", "data-testid": "befehlspalette" }, eingabe, lb);
  d.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); aktiv = Math.min(aktiv + 1, treffer.length - 1); zeichnen(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); aktiv = Math.max(aktiv - 1, 0); zeichnen(); }
    else if (e.key === "Enter") { e.preventDefault(); ausfuehren(aktiv); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); zu(true); }
  });
  document.body.append(d);
  paletteOffen = d;
  fuellen();
  eingabe.focus();
}

// ------------------------------------------------------------------ globale Tasten
function schliesseEbenen() { schliesseMenue(false); schliesseDialog(false); paletteOffen?.remove(); paletteOffen = null; }
document.addEventListener("keydown", (e) => {
  const strgTaste = e.ctrlKey || e.metaKey;
  if (strgTaste && !e.altKey && (e.key.toLowerCase() === "k" || (e.shiftKey && e.key.toLowerCase() === "p"))) { e.preventDefault(); palette(); return; }
  if (e.key === "Escape") {
    if (nav.classList.contains("offen")) { menueZu(true); return; }
    if (!menue && !dialog && !paletteOffen && liste && document.contains(liste.grid)) setzeAuswahl(new Set());
    return;
  }
  const inFeld = e.target.closest && e.target.closest("input,select,textarea,[contenteditable]");
  if (inFeld) {
    if (e.target === tid("suche-feld") && e.key === "Enter") gehe("/suche?q=" + encodeURIComponent(e.target.value));
    return;
  }
  if (e.altKey && (/^[1-7]$/.test(e.key) || (mut("m28_alt_acht") && e.key === "8"))) { e.preventDefault(); gehe(NAV.find((x) => x[0] === ALT[Number(e.key) - 1])[1]); }
  else if (e.key === "/") { e.preventDefault(); tid("suche-feld").focus(); }
});

(async () => {
  try { const s = await rest("GET", "/api/anmeldung"); csrf = s.csrf_token; } catch (e) { /* ohne Anmeldung */ }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  if (mut("m13_ohne_neuladen")) ueberVorrat = await rest("GET", "/api/version");
  await zeige();
})();


// ------------------------------------------------------------------ M16: Begründung (oberflaeche.md 26)
const ROLLE = { glied: (g) => "Glied " + g, zusaetzlich: () => "zusätzlich", vor_beginn: () => "vor Beginn", keine_serie: () => "–" };
async function begruendungOeffnen(bid, ausloeser) {
  if (bid === null || bid === undefined) return;
  let r;
  try { r = await rest("GET", `/api/buchungen/${bid}/wiederkehrend`); } catch (e) { meldung(e.message, "fehler"); return; }
  const ja = r.urteil === "wiederkehrend";
  const inhalt = [h("p", { "data-testid": "wk-urteil", "data-urteil": r.urteil, text: (ja ? "Wiederkehrend? Ja" : "Wiederkehrend? Nein") + " – " + r.text }),
    h("p", { text: "Stichtag: " + datum(r.stichtag) })];
  if (!r.eintraege.length) inhalt.push(h("p", { "data-testid": "wk-text", text: r.text }));
  for (const e of r.eintraege) {
    const zeilen = e.buchungen.map((b) => h("tr", { "data-testid": "wk-buchung", "data-id": b.buchung_id, "data-rolle": b.rolle,
      class: b.buchung_id === bid && !mut("m16_dialog_ohne_markierung") ? "wk-betroffen" : null },
      h("td", { text: datum(b.datum) }), h("td", { "data-betrag": b.betrag, text: betrag(b.betrag) }),
      h("td", { text: ROLLE[b.rolle](b.glied) + (b.buchung_id === bid ? " (diese Buchung)" : "") })));
    const rhythmen = e.rhythmen.map((rh, i) => h("details", { "data-testid": "wk-rhythmus-" + rh.rhythmus, open: i === e.rhythmen.length - 1 },
      h("summary", { text: `${rh.rhythmus}: Länge ${rh.laenge}, Mindestanzahl ${rh.mindestanzahl}, ${rh.erfuellt ? "erfüllt" : "nicht erfüllt"}` }),
      h("ol", {}, rh.schritte.map((st) => {
        const beteiligt = [st.von, st.vorgaenger, st.fremd, ...(mut("m16_schritt_betroffen_nur_von") ? [] : st.uebersprungen)]
          .some((x) => x && x.buchung_id === bid);
        return h("li", { "data-testid": "wk-schritt", "data-ergebnis": st.ergebnis, "data-grund": st.grund, class: beteiligt ? "wk-betroffen" : null, text: st.text });
      }))));
    inhalt.push(h("section", { "data-testid": "wk-eintrag", "data-urteil": e.urteil },
      h("h3", { text: e.gruppe }), h("p", { "data-testid": "wk-eintrag-text", text: e.text }),
      h("p", { text: `Gruppe mit ${e.gruppe_anzahl} Einträgen, Toleranz ±5 Tage` }),
      h("details", { "data-testid": "wk-buchungen" }, h("summary", { text: "Buchungen der Gruppe" }), h("table", {}, h("tbody", {}, zeilen))),
      rhythmen));
  }
  for (const a of r.ausgeschlossen) inhalt.push(h("p", { "data-testid": "wk-ausgeschlossen", text: `${a.konto.name}: ${a.text}` }));
  const zu = h("button", { type: "button", "data-testid": "wk-schliessen", text: "Schließen", "on:click": () => schliesseDialog(!mut("m16_dialog_fokus_weg")) });
  inhalt.push(zu);
  oeffneDialog("wiederkehrend-begruendung", "Warum (nicht) wiederkehrend?", inhalt, mut("m16_dialog_fokus_weg") ? null : ausloeser);
  zu.focus();
}

async function wiederkehrendSeite() {
  const u = await rest("GET", "/api/wiederkehrend");
  if (!u.serien.length) return seite("wiederkehrend", "Wiederkehrende Buchungen", h("p", { text: "Keine wiederkehrenden Buchungen erkannt." }));
  const menue = (s, ausloeser, x, y) => {
    const id = mut("m16_serie_erste_buchung") ? s.buchung_ids[0] : s.buchung_ids[s.buchung_ids.length - 1];
    zeigeMenue(ausloeser, x, y, [["km-serie-begruendung", "Warum wiederkehrend?", true, () => begruendungOeffnen(id, ausloeser)],
      ["km-serie-springen", "Letzte Buchung im Kontoblatt zeigen", true, () => gehe(`/konten/${s.konto_id}?buchung=${id}`)]]);
  };
  const zeilen = u.serien.map((s) => {
    const knopf = h("button", { type: "button", "data-testid": "wk-menue-" + s.schluessel, "aria-haspopup": "menu", "aria-label": "Aktionen für " + s.empfaenger.name, text: "…" });
    const z = h("tr", { "data-testid": "serie-" + s.schluessel, tabindex: "0", "data-status": s.status },
      h("td", { text: s.empfaenger.name }), h("td", { text: s.rhythmus }), h("td", { "data-betrag": s.betrag, text: betrag(s.betrag) }),
      h("td", { "data-betrag": s.jahreskosten, text: betrag(s.jahreskosten) }), h("td", { "data-datum": s.naechste_faelligkeit, text: datum(s.naechste_faelligkeit) }),
      h("td", {}, knopf));
    knopf.addEventListener("click", (e) => { const r = knopf.getBoundingClientRect(); menue(s, knopf, r.left, r.bottom); e.stopPropagation(); });
    z.addEventListener("contextmenu", (e) => { e.preventDefault(); menue(s, z, e.clientX, e.clientY); });
    z.addEventListener("keydown", (e) => {
      if (e.target !== z) return;
      if ((e.shiftKey && e.key === "F10") || e.key === "ContextMenu") { e.preventDefault(); const r = z.getBoundingClientRect(); menue(s, z, r.left + 20, r.bottom); }
    });
    return z;
  });
  const tabelle = h("table", { "data-testid": "wiederkehrend-tabelle" },
    h("thead", {}, h("tr", {}, ["Empfänger", "Rhythmus", "Betrag", "Jahreskosten", "Nächste Fälligkeit"].map((t) => h("th", { text: t })),
      h("th", {}, h("span", { class: "sr-only", text: "Aktionen" })))), h("tbody", {}, zeilen));
  return seite("wiederkehrend", "Wiederkehrende Buchungen", tabelle);
}

async function sprungziel(q) {
  const wert = q.get("buchung");
  if (wert === null) return;
  if (!/^[0-9]+$/.test(wert)) return;
  const id = Number(wert);
  if (!mut("m16_sprung_ohne_nachladen")) {
    while (!liste.buchungen.has(id) && liste.zeilen.length < liste.gesamt) { liste.seiten += 1; await neuLaden(); }
  }
  if (!mut("m16_sprung_parameter_bleibt")) {
    const p = new URLSearchParams(location.search); p.delete("buchung");
    history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : ""));
  }
  if (!liste.buchungen.has(id)) { meldung("Die Buchung ist mit den gesetzten Filtern nicht in der Liste.", "hinweis"); return; }
  setzeAuswahl(new Set([id])); liste.anker = id; setzeFokus(id);
  const z = tid("buchung-" + id, liste.grid);
  z.scrollIntoView({ block: "center" }); z.classList.add("hervorgehoben");
  setTimeout(() => z.classList.remove("hervorgehoben"), 2000);
}
