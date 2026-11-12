/* Kontor – Einstieg der Oberfläche: Router (History API), Grundgerüst, Tastaturkürzel, Befehlspalette, Design,
 * mobiles Menü, Synchronisation mit PIN-Dialog, Service Worker und Offline-Hinweis (oberflaeche.md 1–4, 11, 12,
 * 15.4, 16–19). */
import {
  ApiFehler, BESTAND, anmeldung, anmeldungLaden, api, beiOffline, dialogOffen, ebeneOeffnen, ebeneSchliessen, ebenen,
  fehlerMelden, h, istTexteingabe, kontoNach, melde, nachName, neueId, oberflaeche, obersteEbene, passt, rueckgaengig, stamm,
  stammLaden, stapelAnzeigen, tid, wiederholen,
} from "./kern.js";
import { bestaetigen, dialog, feld, fokusFalle, imDialog, knopf, knopfLeiste, zuordnungDialog } from "./ui.js";
import { begruendungZeigen, kontoSeite, layoutZuruecksetzen, markierteBuchung } from "./konto.js";
import * as S from "./seiten.js";
import { erwartetSeite } from "./erwartet.js";
import { Tabs } from "./tabs.js";

const app = tid("app");
const haupt = tid("hauptbereich");
const navigation = tid("navigation");
const menueKnopf = tid("menue-knopf");

// ------------------------------------------------------------------ Design (17)
const THEMA_SCHLUESSEL = "kontor.thema";
const dunkelAbfrage = window.matchMedia("(prefers-color-scheme: dark)");
const thema = {
  lesen() {
    let t = null;
    try { t = localStorage.getItem(THEMA_SCHLUESSEL); } catch (e) { /* Speicher nicht verfügbar: Vorgabe */ }
    return ["system", "hell", "dunkel"].includes(t) ? t : "system";
  },
  setzen(t) {
    try {
      if (t === "system") localStorage.removeItem(THEMA_SCHLUESSEL);
      else localStorage.setItem(THEMA_SCHLUESSEL, t);
    } catch (e) { /* Speicher nicht verfügbar: gilt nur in diesem Fenster */ }
    thema.anwenden();
    const sel = tid("einstellung-thema");
    if (sel) sel.value = t;
  },
  anwenden() {
    const t = thema.lesen();
    const wirksam = t === "system" ? (dunkelAbfrage.matches ? "dunkel" : "hell") : t;
    document.documentElement.dataset.thema = wirksam;
  },
};
thema.anwenden();
dunkelAbfrage.addEventListener("change", () => thema.anwenden());

// ------------------------------------------------------------------ Layout (16.1)
const mobilAbfrage = window.matchMedia("(max-width: 767.98px)");
const istMobil = () => mobilAbfrage.matches;
oberflaeche.istMobil = istMobil;

function layoutSetzen() {
  app.dataset.layout = istMobil() ? "mobil" : "desktop";
  menueSchliessen(false);
  if (aktuell && aktuell.seite && aktuell.seite.layoutGeaendert) aktuell.seite.layoutGeaendert();
}
mobilAbfrage.addEventListener("change", layoutSetzen);
app.dataset.layout = istMobil() ? "mobil" : "desktop";

// ------------------------------------------------------------------ Mobiles Menü (16.2)
const hintergrund = tid("menue-hintergrund");
let menueEbene = null;

function menueOeffnen() {
  if (menueEbene) return;
  app.classList.add("menue-offen");
  hintergrund.hidden = false;
  menueKnopf.setAttribute("aria-expanded", "true");
  menueKnopf.setAttribute("aria-label", "Navigation ausblenden");
  menueEbene = ebeneOeffnen({ art: "menue-mobil", escape: () => menueSchliessen(true),
    tab: (e) => fokusFalle(navigation, e) });
  const erster = navigation.querySelector("a");
  if (erster) erster.focus();
}

function menueSchliessen(fokusZurueck) {
  if (!menueEbene) return;
  ebeneSchliessen(menueEbene);
  menueEbene = null;
  app.classList.remove("menue-offen");
  hintergrund.hidden = true;
  menueKnopf.setAttribute("aria-expanded", "false");
  menueKnopf.setAttribute("aria-label", "Navigation einblenden");
  if (fokusZurueck) menueKnopf.focus();
}

menueKnopf.addEventListener("click", () => (menueEbene ? menueSchliessen(true) : menueOeffnen()));

// ------------------------------------------------------------------ Über Kontor (D-105)
const versionKnopf = tid("version-knopf");

async function ueberOeffnen() {
  menueSchliessen(false);
  let info;
  try { info = await api("GET", "/api/version"); } catch (e) { behandeln(e); return; }
  const zeile = (testid, titel, wert) => h("tr", null, h("th", { scope: "row" }, titel), h("td", { tid: testid }, wert));
  const build = info.entwicklungsstand ? "Entwicklungsstand (nicht über die Release-CI gebaut)"
    : [info.build_datum, info.commit].filter(Boolean).join(" · ") || "–";
  dialog("ueber-dialog", `Über ${info.name}`, (inhalt, d) => {
    inhalt.append(
      h("p", { class: "ueber-version" }, h("strong", { tid: "ueber-version" }, `Version ${info.version}`)),
      h("table", { class: "ueber-tabelle" }, h("tbody", null,
        zeile("ueber-build", "Build", build),
        zeile("ueber-modus", "Modus", info.modus === "mock" ? "Mock-Modus" : "Echtbetrieb"),
        zeile("ueber-python", "Python", info.python),
        zeile("ueber-datenbank", "Datenbank", info.datenbank),
        zeile("ueber-schema", "Schemaversion", `Datenbank ${info.datenbank_schema} · Sicherung ${info.sicherung_schema}`),
        h("tr", null, h("th", { scope: "row" }, "Quellcode"), h("td", null, h("a", { tid: "ueber-repository",
          href: info.repository, target: "_blank", rel: "noopener noreferrer" }, info.repository))))),
      updateBereich(d, info),
      knopfLeiste(knopf("Schließen", { tid: "ueber-schliessen", onclick: () => d.schliessen(null) })));
  }, { ausloeser: istMobil() ? menueKnopf : versionKnopf, schliessenKnopf: "ueber-x", fokus: (box) => box.querySelector("[data-testid=ueber-schliessen]") });
}
versionKnopf.addEventListener("click", ueberOeffnen);

// ------------------------------------------------------------------ Aktualisierung (D-107)
const UPDATE_ABFRAGE_MS = 60 * 60 * 1000;

/** Punkt am Versionsknopf (und mobil am Menüknopf), wenn eine neuere Version verfügbar ist. */
function updateAnzeigen(st) {
  const neu = !!(st && st.verfuegbar);
  for (const el of [versionKnopf, menueKnopf]) {
    if (!el) continue;
    if (neu) el.dataset.update = "verfuegbar"; else delete el.dataset.update;
  }
  versionKnopf.title = neu ? `Über Kontor – Version ${st.neueste_version} ist verfügbar` : "Über Kontor";
}

async function updateLaden() {
  try { const st = await api("GET", "/api/update"); updateAnzeigen(st); return st; } catch (e) { return null; }
}

function zeitText(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

/** Abschnitt „Aktualisierung“ im About-Dialog: Stand, „Jetzt prüfen“, „Aktualisieren“. */
function updateBereich(d, info) {
  const status = h("p", { tid: "ueber-update-status", "aria-live": "polite" }, "Suche nach Aktualisierungen …");
  const ergebnis = h("p", { tid: "ueber-update-ergebnis", class: "hinweis", hidden: true });
  const pruefen = knopf("Jetzt prüfen", { tid: "ueber-update-pruefen" });
  const installieren = knopf("Aktualisieren", { tid: "ueber-update-installieren", class: "knopf knopf-haupt", hidden: true });
  const bereich = h("section", { class: "ueber-update", tid: "ueber-update", "aria-label": "Aktualisierung" },
    h("h3", null, "Aktualisierung"), status, ergebnis, knopfLeiste(installieren, pruefen));
  if (info.modus === "mock") {
    status.textContent = "Im Mock-Modus wird nicht nach Aktualisierungen gesucht.";
    pruefen.hidden = true;
    return bereich;
  }
  let stand = null;
  const zeigen = (st) => {
    stand = st;
    updateAnzeigen(st);
    bereich.dataset.verfuegbar = st.verfuegbar ? "ja" : "nein";
    let text;
    if (st.laeuft) text = "Die Aktualisierung läuft. Kontor startet danach neu.";
    else if (st.verfuegbar) text = `Version ${st.neueste_version} ist verfügbar (installiert: ${st.version}).`;
    else if (st.fehler) text = `Suche fehlgeschlagen: ${st.fehler}`;
    else if (st.neueste_version) text = `Kontor ist auf dem neuesten Stand (${st.version}).`;
    else text = "Noch nicht nach Aktualisierungen gesucht.";
    if (st.geprueft_um && !st.laeuft) text += ` Zuletzt geprüft: ${zeitText(st.geprueft_um)}.`;
    if (!st.automatisch && !st.laeuft) text += " Automatische Suche abgeschaltet.";
    if (st.verfuegbar && !st.eingerichtet) text += " Der Update-Dienst ist nicht eingerichtet (siehe README).";
    status.textContent = text;
    if (st.verfuegbar && st.release_url) {
      status.append(" ", h("a", { href: st.release_url, target: "_blank", rel: "noopener noreferrer",
        tid: "ueber-update-notizen" }, "Versionshinweise"));
    }
    const e = st.letztes_ergebnis;
    ergebnis.hidden = !e;
    if (e) {
      ergebnis.dataset.erfolg = e.erfolg ? "ja" : "nein";
      ergebnis.textContent = `Letzte Aktualisierung${e.zeit ? ` (${zeitText(e.zeit)})` : ""}: ${e.meldung}`;
    }
    installieren.hidden = !st.installierbar;
    installieren.textContent = st.installierbar ? `Auf ${st.neueste_version} aktualisieren` : "Aktualisieren";
    pruefen.disabled = st.laeuft;
  };
  pruefen.addEventListener("click", () => imDialog(d, pruefen, async () => {
    status.textContent = "Suche nach Aktualisierungen …";
    zeigen(await api("POST", "/api/update/pruefen", {}));
  }));
  installieren.addEventListener("click", async () => {
    if (!stand || !stand.installierbar) return;
    const ziel = stand.neueste_version;
    const ok = await bestaetigen(`Kontor auf Version ${ziel} aktualisieren? Vorher wird eine Datensicherung angelegt; `
      + "danach startet Kontor neu und ist kurz nicht erreichbar.", { ja: "Aktualisieren", ausloeser: installieren });
    if (!ok) return;
    await imDialog(d, installieren, async () => {
      zeigen(await api("POST", "/api/update/installieren", { version: ziel }));
      warteAufNeustart(ziel, status);
    });
  });
  updateLaden().then((st) => { if (st && d.offen) zeigen(st); });
  return bereich;
}

/** Nach dem Auftrag: /api/version abfragen, bis die neue Version antwortet, dann die Seite neu laden. */
function warteAufNeustart(ziel, status) {
  const ende = Date.now() + 20 * 60 * 1000;
  const runde = async () => {
    if (Date.now() > ende) { melde("fehler", "Die Aktualisierung dauert ungewöhnlich lange. Siehe journalctl -u kontor-update."); return; }
    try {
      const v = await api("GET", "/api/version");
      if (v.version === ziel) { location.reload(); return; }
      const st = await api("GET", "/api/update");
      if (!st.laeuft && st.letztes_ergebnis && !st.letztes_ergebnis.erfolg) {
        if (status.isConnected) status.textContent = `Aktualisierung fehlgeschlagen: ${st.letztes_ergebnis.meldung}`;
        melde("fehler", `Aktualisierung fehlgeschlagen: ${st.letztes_ergebnis.meldung}`);
        return;
      }
    } catch (e) { /* Kontor startet gerade neu */ }
    setTimeout(runde, 3000);
  };
  setTimeout(runde, 3000);
}
updateLaden();
setInterval(updateLaden, UPDATE_ABFRAGE_MS);
hintergrund.addEventListener("click", () => menueSchliessen(true));

// ------------------------------------------------------------------ Routen (3)
const ROUTEN = [
  [/^\/$/, "uebersicht", "uebersicht", S.uebersicht],
  [/^\/konten$/, "konten", "konten", S.konten],
  [/^\/konten\/(\d+)$/, "konto", "konten", (seite, id, suche) => kontoSeite(seite, id, suche)],
  [/^\/kategorien$/, "kategorien", "kategorien", S.kategorienSeite],
  [/^\/wiederkehrend$/, "wiederkehrend", "wiederkehrend", S.wiederkehrend],
  [/^\/erwartet$/, "erwartet", null, erwartetSeite],
  [/^\/kredite$/, "kredite", "kredite", S.kredite],
  [/^\/kredite\/(\d+)$/, "kredit", "kredite", S.kredit],
  [/^\/berichte$/, "berichte", "berichte", S.berichte],
  [/^\/import$/, "import", "import", S.importSeite],
  [/^\/einstellungen$/, "einstellungen", "einstellungen", S.einstellungen],
  [/^\/protokoll$/, "protokoll", "protokoll", S.protokoll],
  [/^\/empfaenger$/, "empfaenger", "empfaenger", S.empfaenger],
  [/^\/regeln$/, "regeln", "regeln", S.regeln],
  [/^\/vorlagen$/, "vorlagen", "vorlagen", S.vorlagen],
  [/^\/dubletten$/, "dubletten", "dubletten", S.dubletten],
  [/^\/sync(?:\/konten)?$/, "sync", "sync", S.syncSeite],
  [/^\/benachrichtigungen$/, "benachrichtigungen", null, S.benachrichtigungen],
  [/^\/suche$/, "suche", null, S.suche],
  [/^\/tan\/(\d+)$/, "tan", null, S.tan],
  [/^\/mail\/postfaecher\/(\d+)$/, "postfach", "einstellungen", S.postfach],
  [/^\/buchungen\/(\d+)$/, "buchung", null, S.buchung],
];
const NAV_ZIELE = ["uebersicht", "konten", "kategorien", "wiederkehrend", "kredite", "berichte", "import", "einstellungen"];

let aktuell = null;
let renderNr = 0;
let offline = false;
const kontext = {
  thema,
  abmelden,
  synchronisieren,
  neuZeigen: () => zeigen({ behalten: true }),
};

function navMarkieren(ziel) {
  for (const a of navigation.querySelectorAll("a[data-testid^='nav-']")) {
    if (a.dataset.testid === `nav-${ziel}`) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

class NichtGefunden extends Error {}

// ------------------------------------------------------------------ Tabs (D-119)
// Jede Ansicht ist ein Tab (Schlüssel: Pfad ohne Abfrageteil). Ein offener Tab behält DOM und Seitenobjekt; beim
// Wechsel wird nur das DOM getauscht. Eine Änderung am Buchbestand markiert die übrigen Tabs als veraltet; sie laden
// beim nächsten Zeigen mit dem Stand des Servers neu.
const tabs = new Tabs(tid("tab-leiste"), haupt, {
  beiWahl: (t) => gehe(t.pfad + t.suche, false, { vonTab: true }),
  beiSchliessen: (t, naechster) => {
    if (naechster) gehe(naechster.pfad + naechster.suche, true);
    else gehe("/", true);
  },
});
oberflaeche.urlGeaendert = () => tabs.urlGeaendert();

/** Einen offenen, geladenen Tab wieder zeigen (ohne Neuaufbau). Über Navigation oder Link angefordert (nicht über
 * den Tab selbst oder Zurück/Vor) beginnt die Filterleiste wieder eingeklappt (oberflaeche.md 23.1, E-172). */
async function tabZeigen(t, route, o) {
  haupt.replaceChildren(t.el);
  aktuell = t;
  tabs.aktivieren(t);
  navMarkieren(route ? route[2] : null);
  titelSetzen(t.titel);
  tabs.scrollHerstellen(t);
  if (t.layout !== app.dataset.layout && t.seite && t.seite.layoutGeaendert) t.seite.layoutGeaendert();
  t.layout = app.dataset.layout;
  if (o.inApp && !o.vonTab && t.seite && t.seite.wiederAngefordert) t.seite.wiederAngefordert();
  if (t.veraltet) {
    t.veraltet = false;
    if (t.seite && t.seite.aktualisieren) {
      try { await stammLaden(); await t.seite.aktualisieren(); } catch (e) { behandeln(e); }
    } else {
      return false;   // Seite ohne eigenes Aktualisieren: neu aufbauen
    }
  }
  app.dataset.bereit = "ja";
  return true;
}

async function zeigen(optionen) {
  const o = optionen || {};
  const nr = ++renderNr;
  const pfad = location.pathname;
  let route = null;
  let parameter = null;
  for (const r of ROUTEN) {
    const m = r[0].exec(pfad);
    if (m) { route = r; parameter = m[1]; break; }
  }
  const name = route ? route[1] : "nicht-gefunden";
  const offen = tabs.finden(pfad);
  // Navigation innerhalb der Oberfläche ohne Abfrageteil: der offene Tab behält Filter und Sortierung
  if (o.inApp && offen && location.search === "" && offen.suche) history.replaceState(null, "", pfad + offen.suche);
  const suche = location.search;
  // Kontoansicht bei einem Neuladen nach einer Änderung: Auswahl und Fokus bleiben (7.4)
  if (o.behalten && aktuell && aktuell.name === name && aktuell.pfad === pfad && aktuell.seite && aktuell.seite.aktualisieren
      && aktuell.el.isConnected) {
    tabs.andereVeraltet(aktuell);
    try { await stammLaden(); await aktuell.seite.aktualisieren(); } catch (e) { behandeln(e); }
    return;
  }
  if (o.behalten) tabs.andereVeraltet(aktuell);
  if (aktuell !== offen || !o.behalten) tabs.verlassen();
  // Wechsel zu einem offenen Tab: Zustand bleibt, solange der Abfrageteil passt
  if (!o.behalten && !o.erneut && offen && offen !== aktuell && offen.geladen && offen.el && offen.suche === suche && !offline) {
    if (await tabZeigen(offen, route, o)) return;
  }
  const tab = tabs.holen(pfad, suche);
  tab.suche = suche;
  const el = h("section", { class: `seite seite-${name}`, tid: `seite-${name}`, "data-geladen": "nein" });
  const scrollVorher = o.behalten ? haupt.scrollTop : 0;
  const gleich = aktuell === tab && aktuell.name === name;
  if (!o.behalten || !gleich) haupt.replaceChildren(el);
  if (!o.behalten) haupt.scrollTop = 0;
  aktuell = tab;
  Object.assign(tab, { name, el, seite: null, geladen: false, veraltet: false, scroll: null, layout: app.dataset.layout });
  tabs.aktivieren(tab);
  navMarkieren(route ? route[2] : null);
  try {
    if (!route) throw new NichtGefunden();
    if (offline) throw new ApiFehler(0, { meldung: "offline" });
    await stammLaden();
    if (nr !== renderNr) return;
    const seite = await route[3](el, parameter, suche, kontext);
    if (nr !== renderNr) return;
    if (o.behalten) haupt.replaceChildren(el);
    Object.assign(tab, { seite: seite || null, geladen: true });
    const titel = (seite && seite.titel) || titelVon(name);
    tabs.titelSetzen(tab, titel);
    titelSetzen(seite && seite.titel);
    el.dataset.geladen = "ja";
    if (o.behalten) haupt.scrollTop = scrollVorher;
  } catch (e) {
    if (nr !== renderNr) return;
    if (e instanceof NichtGefunden || (e instanceof ApiFehler && e.status === 404)) {
      const nf = h("section", { class: "seite seite-nicht-gefunden", tid: "seite-nicht-gefunden", "data-geladen": "ja" },
        h("h1", null, "Nicht gefunden"), h("p", null, "Diese Seite oder dieses Objekt gibt es nicht. "),
        h("p", null, h("a", { href: "/" }, "Zur Finanzübersicht")));
      haupt.replaceChildren(nf);
      navMarkieren(route && name === "konto" ? "konten" : null);
      Object.assign(tab, { name: "nicht-gefunden", el: nf, seite: null, geladen: false });
      tabs.titelSetzen(tab, "Nicht gefunden");
      titelSetzen("Nicht gefunden");
    } else {
      Object.assign(tab, { el, seite: null, geladen: false });
      if (!el.querySelector("h1")) el.prepend(h("h1", null, titelVon(name)));
      tabs.titelSetzen(tab, tab.titel || titelVon(name));
      titelSetzen(titelVon(name));
      behandeln(e);
    }
  }
  app.dataset.bereit = "ja";
}

const TITEL = { uebersicht: "Finanzübersicht", konten: "Konten", konto: "Konto", kategorien: "Kategorien",
  wiederkehrend: "Wiederkehrende Buchungen", kredite: "Kredite", kredit: "Kredit", berichte: "Berichte", import: "Import",
  einstellungen: "Einstellungen", protokoll: "Änderungsprotokoll", empfaenger: "Empfänger", regeln: "Regeln",
  vorlagen: "Split-Vorlagen", dubletten: "Dubletten", sync: "Synchronisation", benachrichtigungen: "Benachrichtigungen",
  suche: "Suche", tan: "TAN-Freigabe", postfach: "Postfach", buchung: "Buchung", erwartet: "Was kommt noch?" };
const titelVon = (n) => TITEL[n] || "Kontor";

function titelSetzen(t) {
  document.title = (t || "Kontor") + " – Kontor";
}

function behandeln(e) {
  if (e && e.offline) { offlineSetzen(true); return; }
  if (e && e.message === "offline") return;
  fehlerMelden(e);
}

oberflaeche.neuLaden = () => zeigen({ behalten: true });

export function gehe(pfad, ersetzen, optionen) {
  menueSchliessen(false);
  // dieselbe Ansicht erneut aufrufen baut sie neu auf (wie bisher)
  if (pfad === location.pathname + location.search) return zeigen({ erneut: true });
  // aktiver Tab mit Filtern ohne Abfrageteil angefordert: Zustand bleibt, Filterleiste eingeklappt (D-119)
  if (pfad === location.pathname && aktuell && aktuell.pfad === pfad && aktuell.geladen && aktuell.el.isConnected) {
    if (aktuell.seite && aktuell.seite.wiederAngefordert && !(optionen && optionen.vonTab)) aktuell.seite.wiederAngefordert();
    return Promise.resolve();
  }
  tabs.verlassen();
  if (ersetzen) history.replaceState(null, "", pfad); else history.pushState(null, "", pfad);
  return zeigen({ inApp: true, ...(optionen || {}) });
}
oberflaeche.gehe = gehe;

/** Gehe zur Gegenbuchung: Kontoansicht des Kontos (Tab) zeigen und dort die Buchung markieren. */
oberflaeche.zurBuchung = async (kontoId, buchungId) => {
  const ziel = `/konten/${kontoId}`;
  if (location.pathname !== ziel) await gehe(ziel);
  if (aktuell && aktuell.pfad === ziel && aktuell.seite && aktuell.seite.buchungZeigen) await aktuell.seite.buchungZeigen(buchungId);
};

window.addEventListener("popstate", () => { tabs.verlassen(); zeigen(); });

document.addEventListener("click", (e) => {
  if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
  const a = e.target.closest && e.target.closest("a[href]");
  if (!a || a.target || a.hasAttribute("download")) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/") || url.pathname.startsWith("/oeffentlich/")
      || url.pathname === "/anmelden") return;
  e.preventDefault();
  gehe(url.pathname + url.search);
});

// ------------------------------------------------------------------ Kopfzeile (4.2)
document.getElementById("suche-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = tid("suche-feld").value.trim();
  if (q) gehe("/suche?q=" + encodeURIComponent(q));
});
tid("rueckgaengig-knopf").addEventListener("click", () => rueckgaengig());
tid("wiederholen-knopf").addEventListener("click", () => wiederholen());
tid("befehlspalette-knopf").addEventListener("click", (e) => palette(e.currentTarget));
tid("sync-starten").addEventListener("click", () => synchronisieren());

async function benachrichtigungenZaehlen() {
  if (offline) return;
  try {
    const liste = await api("GET", "/api/benachrichtigungen?gelesen=false");
    const z = tid("benachrichtigungen-anzahl");
    z.dataset.anzahl = String(liste.length);
    z.textContent = liste.length ? String(liste.length) : "";
    z.classList.toggle("sichtbar", liste.length > 0);
    tid("benachrichtigungen-knopf").setAttribute("aria-label",
      liste.length ? `Benachrichtigungen (${liste.length} ungelesen)` : "Benachrichtigungen");
  } catch (e) { if (e.offline) offlineSetzen(true); }
}
oberflaeche.benachrichtigungen = benachrichtigungenZaehlen;

// ------------------------------------------------------------------ Synchronisation und PIN (15.4)
let syncLaeuft = false;

async function synchronisieren() {
  if (syncLaeuft) return;
  syncLaeuft = true;
  const knopfEl = tid("sync-starten");
  knopfEl.disabled = true;
  let lauf = null;
  try {
    lauf = await api("POST", "/api/sync", {});
    syncErgebnis(lauf);
  } catch (e) {
    fehlerMelden(e);
  } finally {
    syncLaeuft = false;
    knopfEl.disabled = false;
    await zeigen({ behalten: true });
    await benachrichtigungenZaehlen();
  }
  if (lauf) await zuordnenNachLauf(lauf);
}

const LAUF = { erfolgreich: "Synchronisation erfolgreich.", fehlgeschlagen: "Synchronisation fehlgeschlagen.",
  wartet_auf_tan: "Die Bank verlangt eine TAN-Freigabe.", abgebrochen: "Synchronisation abgebrochen.", laeuft: "Synchronisation läuft." };
const PIN_FEHLER = new Set(["bank_pin_fehlt", "bank_pin_falsch"]);

const nichtZugeordnet = (lauf) => (lauf.uebersprungen || []).filter((u) => u.status === "nicht_zugeordnet");

function laufText(lauf) {
  const neu = (lauf.konten || []).reduce((s, k) => s + (k.buchungen_neu || 0), 0);
  const offen = nichtZugeordnet(lauf).length;
  return (LAUF[lauf.status] || lauf.status) + (lauf.status === "erfolgreich" ? ` ${neu === 1 ? "1 neue Buchung" : `${neu} neue Buchungen`}.` : "")
    + (offen ? ` ${offen === 1 ? "Ein Bankkonto ist" : `${offen} Bankkonten sind`} noch keinem Konto zugeordnet.` : "")
    + (lauf.fehler && lauf.fehler.meldung ? " " + lauf.fehler.meldung : "");
}

function syncErgebnis(lauf, pinDialogOffen) {
  const code = lauf.fehler && lauf.fehler.code;
  if (PIN_FEHLER.has(code)) {
    if (pinDialogOffen) return lauf;
    pinDialog(code === "bank_pin_falsch");
    return lauf;
  }
  if (lauf.status === "wartet_auf_tan" && lauf.tan_anforderung_id) {
    melde("hinweis", LAUF.wartet_auf_tan, { link: { href: `/tan/${lauf.tan_anforderung_id}`, tid: "sync-tan-link", text: "TAN eingeben" } });
  } else {
    melde(lauf.status === "erfolgreich" ? "erfolg" : lauf.status === "fehlgeschlagen" ? "fehler" : "hinweis", laufText(lauf));
  }
  return lauf;
}

/** D-111: Nach einem Lauf für jedes nicht zugeordnete Bankkonto die Zuordnung anbieten, danach erneut abrufen. */
async function zuordnenNachLauf(lauf) {
  const offen = nichtZugeordnet(lauf);
  if (!offen.length || PIN_FEHLER.has(lauf.fehler && lauf.fehler.code)) return;
  let zugeordnet = 0;
  for (const bk of offen) {
    const w = await zuordnungDialog(bk, tid("sync-starten"),
      offen.length > 1 ? `Bankkonto ${offen.indexOf(bk) + 1} von ${offen.length}.` : null);
    if (w === null) break;
    if (w) zugeordnet += 1;
  }
  if (zugeordnet) await synchronisieren();   // Umsätze der eben zugeordneten Bankkonten abrufen
}

/**
 * Statusanzeige während eines Laufs: fragt `GET /api/sync/status` ab, solange `POST /api/sync` läuft, und meldet
 * den Fortschritt je Bankkonto (Zuordnung, Abruf, TAN).
 */
function laufBeobachten(zeigenText) {
  let aktiv = true;
  (async () => {
    await new Promise((r) => setTimeout(r, 400));
    while (aktiv) {
      try {
        const st = await api("GET", "/api/sync/status");
        const l = st.letzter_lauf;
        if (aktiv && l && l.status === "laeuft") {
          const konten = l.konten || [];
          const fertig = konten.filter((k) => k.status !== "ausstehend").length;
          if (!konten.length) zeigenText("verbinden", "Verbinde mit der Bank …");
          else {
            const aktuell = konten.find((k) => k.status === "ausstehend");
            const name = aktuell ? (kontoNach(aktuell.konto_id) || {}).name || aktuell.iban : "";
            zeigenText("abruf", `Rufe Umsätze ab … (${Math.min(fertig + 1, konten.length)} von ${konten.length}${name ? `: ${name}` : ""})`);
          }
        }
      } catch (e) { /* Anzeige bleibt */ }
      await new Promise((r) => setTimeout(r, 700));
    }
  })();
  return { stop() { aktiv = false; } };
}

function pinDialog(falsch) {
  dialog("pin-dialog", "Bank-PIN eingeben", (inhalt, d) => {
    const pin = h("input", { type: "password", tid: "pin-eingabe", autocomplete: "off", maxlength: "64", spellcheck: "false" });
    const senden = knopf("PIN senden und synchronisieren", { tid: "pin-senden", class: "knopf knopf-haupt" });
    const abbrechen = knopf("Abbrechen", { tid: "pin-abbrechen", onclick: () => d.schliessen(null) });
    const anzeige = h("p", { tid: "pin-dialog-status", class: "sync-status", role: "status", "aria-live": "polite", hidden: true });
    const spinner = h("span", { class: "kreisel", "aria-hidden": "true", hidden: true });
    const status = (art, text) => {
      anzeige.hidden = !text;
      anzeige.dataset.phase = art || "";
      anzeige.textContent = text || "";
      spinner.hidden = !(art === "pin" || art === "verbinden" || art === "abruf");
    };
    if (falsch) d.fehler("Die Bank hat die PIN abgelehnt. Bitte erneut eingeben.");
    let laeuft = false;
    const los = async () => {
      if (laeuft) return;
      const wert = pin.value;
      pin.value = "";
      d.fehler("");
      if (!wert) { d.fehler("Bitte die PIN eingeben."); return; }
      laeuft = true;
      d.sperren(true);
      status("pin", "Übergebe die PIN …");
      let beobachter = null;
      let lauf = null;
      try {
        await api("PUT", "/api/sync/pin", { pin: wert });
        status("verbinden", "Verbinde mit der Bank …");
        beobachter = laufBeobachten(status);
        lauf = await api("POST", "/api/sync", {});
      } catch (e) {
        if (beobachter) beobachter.stop();
        d.sperren(false);
        laeuft = false;
        status("fehler", "");
        d.fehler(e.message || "Die Synchronisation konnte nicht gestartet werden.");
        pin.focus();
        return;
      }
      beobachter.stop();
      const code = lauf.fehler && lauf.fehler.code;
      if (PIN_FEHLER.has(code)) {
        d.sperren(false);
        laeuft = false;
        status("pin_falsch", "");
        d.fehler("Die Bank hat die PIN abgelehnt. Bitte erneut eingeben.");
        pin.focus();
        return;
      }
      if (lauf.status === "wartet_auf_tan") status("tan", "Die Bank verlangt eine TAN-Freigabe.");
      else status(lauf.status === "erfolgreich" ? "fertig" : "fehler", laufText(lauf));
      await new Promise((r) => setTimeout(r, lauf.status === "erfolgreich" ? 900 : 1800));
      d.sperren(false);
      d.schliessen(true);
      syncErgebnis(lauf, true);
      await zeigen({ behalten: true });
      await benachrichtigungenZaehlen();
      await zuordnenNachLauf(lauf);
    };
    senden.addEventListener("click", los);
    pin.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); los(); } });
    inhalt.append(h("p", null, "Die PIN wird nur im Arbeitsspeicher des Servers gehalten, nie gespeichert."), feld("PIN", pin),
      h("div", { class: "sync-status-zeile" }, spinner, anzeige), knopfLeiste(senden, abbrechen));
  });
}

// ------------------------------------------------------------------ Anmeldung (19)
async function abmelden() {
  try { await api("POST", "/api/anmeldung/abmelden"); } catch (e) { /* trotzdem zur Anmeldeseite */ }
  anmeldung.csrf = null;
  location.assign("/anmelden");
}

// ------------------------------------------------------------------ Befehlspalette (12.3)
const BEFEHLE = [
  ["gehe-uebersicht", "Gehe zu: Finanzübersicht", () => gehe("/")],
  ["gehe-konten", "Gehe zu: Konten", () => gehe("/konten")],
  ["gehe-kategorien", "Gehe zu: Kategorien", () => gehe("/kategorien")],
  ["gehe-wiederkehrend", "Gehe zu: Wiederkehrende Buchungen", () => gehe("/wiederkehrend")],
  ["gehe-erwartet", "Gehe zu: Was kommt noch? (erwartete Zahlungen)", () => gehe("/erwartet")],
  ["gehe-kredite", "Gehe zu: Kredite", () => gehe("/kredite")],
  ["gehe-berichte", "Gehe zu: Berichte", () => gehe("/berichte")],
  ["gehe-import", "Gehe zu: Import", () => gehe("/import")],
  ["gehe-einstellungen", "Gehe zu: Einstellungen", () => gehe("/einstellungen")],
  ["gehe-protokoll", "Gehe zu: Änderungsprotokoll", () => gehe("/protokoll")],
  ["gehe-empfaenger", "Gehe zu: Empfänger", () => gehe("/empfaenger")],
  ["gehe-regeln", "Gehe zu: Regeln", () => gehe("/regeln")],
  ["gehe-vorlagen", "Gehe zu: Split-Vorlagen", () => gehe("/vorlagen")],
  ["gehe-dubletten", "Gehe zu: Dubletten", () => gehe("/dubletten")],
  ["gehe-sync", "Gehe zu: Synchronisation", () => gehe("/sync")],
  ["gehe-benachrichtigungen", "Gehe zu: Benachrichtigungen", () => gehe("/benachrichtigungen")],
  ["rueckgaengig", "Rückgängig", () => rueckgaengig()],
  ["wiederholen", "Wiederholen", () => wiederholen()],
  ["synchronisieren", "Bankkonten jetzt synchronisieren", () => synchronisieren()],
  ["thema-system", "Design: wie System", () => thema.setzen("system")],
  ["thema-hell", "Design: Hell", () => thema.setzen("hell")],
  ["thema-dunkel", "Design: Dunkel", () => thema.setzen("dunkel")],
  ["layout-zuruecksetzen", "Layout zurücksetzen", () => { layoutZuruecksetzen(); melde("erfolg", "Layout zurückgesetzt."); zeigen(); }],
  ["abmelden", "Abmelden", () => abmelden(), () => anmeldung.aktiv],
  ["wiederkehrend-warum", "Markierte Buchung: Warum (nicht) wiederkehrend?", () => begruendungZeigen(markierteBuchung()),
    () => markierteBuchung() !== null],
];

function palette(ausloeser) {
  if (tid("befehlspalette")) return;
  const eintraege = BEFEHLE.filter((b) => !b[3] || b[3]()).map(([id, text, tun]) => ({ id, text, tun }))
    .concat(stamm.konten.filter((k) => BESTAND.has(k.art) && !k.geschlossen).sort(nachName)
      .map((k) => ({ id: `konto-${k.id}`, text: `Konto öffnen: ${k.name}`, tun: () => gehe(`/konten/${k.id}`) })));
  dialog("befehlspalette", "Befehlspalette", (inhalt, d) => {
    const listeId = neueId("befehle");
    const eingabe = h("input", { type: "text", tid: "befehlspalette-eingabe", role: "combobox", "aria-expanded": "true",
      "aria-controls": listeId, "aria-autocomplete": "list", "aria-label": "Befehl oder Konto suchen", autocomplete: "off",
      spellcheck: "false" });
    const liste = h("div", { role: "listbox", id: listeId, tid: "befehlspalette-liste", class: "auswahl-liste",
      "aria-label": "Befehle" });
    let treffer = [];
    let aktiv = 0;
    const ausfuehren = (e) => { d.schliessen(true); Promise.resolve().then(() => e.tun()); };
    function zeichnen() {
      treffer = eintraege.filter((e) => passt(eingabe.value, e.text));
      aktiv = 0;
      liste.replaceChildren(...treffer.map((e, i) => {
        const el = h("div", { role: "option", id: `befehl-${e.id}`, tid: `befehl-${e.id}`, class: "option",
          "aria-selected": i === 0 ? "true" : "false" }, e.text);
        el.addEventListener("click", () => ausfuehren(e));
        return el;
      }));
      markieren(0);
    }
    function markieren(i) {
      const els = [...liste.children];
      if (!els.length) { eingabe.removeAttribute("aria-activedescendant"); return; }
      aktiv = Math.max(0, Math.min(i, els.length - 1));
      els.forEach((el, j) => el.setAttribute("aria-selected", j === aktiv ? "true" : "false"));
      eingabe.setAttribute("aria-activedescendant", els[aktiv].id);
      els[aktiv].scrollIntoView({ block: "nearest" });
    }
    eingabe.addEventListener("input", zeichnen);
    eingabe.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); markieren(aktiv + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); markieren(aktiv - 1); }
      else if (e.key === "Enter") { e.preventDefault(); if (treffer[aktiv]) ausfuehren(treffer[aktiv]); }
    });
    inhalt.append(eingabe, liste);
    zeichnen();
  }, { ausloeser: ausloeser || document.activeElement, klasse: "dialog-palette" });
}

function tastaturHilfe() {
  if (tid("tastatur-hilfe")) return;
  const K = [["Strg+K, ⌘+K, Strg+Umschalt+P", "Befehlspalette"], ["/", "Suche"], ["?", "diese Hilfe"],
    ["Strg+Z", "Rückgängig"], ["Strg+Umschalt+Z, Strg+Y", "Wiederholen"], ["Alt+1 … Alt+8", "Finanzübersicht … Einstellungen"],
    ["Esc", "Menü/Dialog schließen, sonst Auswahl leeren"], ["Pfeiltasten, Pos1, Ende", "Buchung wählen"],
    ["Umschalt+Pfeil", "Bereich auswählen"], ["Strg+Pfeil", "nur den Fokus bewegen"], ["Leertaste", "Buchung zur Auswahl hinzu/weg"],
    ["Strg+A", "alle Buchungen auswählen"], ["F2", "Verwendungszweck bearbeiten"], ["Entf", "Auswahl löschen (mit Rückfrage)"],
    ["Enter", "Einzelheiten zeigen"], ["Umschalt+F10, Kontextmenü-Taste", "Kontextmenü"]];
  dialog("tastatur-hilfe", "Tastaturkürzel", (inhalt, d) => {
    inhalt.append(h("table", { class: "tabelle" }, h("tbody", null, K.map(([k, w]) => h("tr", null, h("th", { scope: "row" }, h("kbd", null, k)),
      h("td", null, w))))), knopfLeiste(knopf("Schließen", { onclick: () => d.schliessen(null) })));
  });
}

// ------------------------------------------------------------------ Globale Tastatur (12.1)
document.addEventListener("keydown", (e) => {
  if (e.defaultPrevented) return;
  const ebene = obersteEbene();
  const strg = e.ctrlKey || e.metaKey;
  const taste = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const imText = istTexteingabe(document.activeElement);
  if (e.key === "Escape") {
    if (ebene) { e.preventDefault(); ebene.escape(); return; }
    if (aktuell && aktuell.seite && aktuell.seite.escape) aktuell.seite.escape();
    return;
  }
  if (e.key === "Tab" && ebene && ebene.tab) { ebene.tab(e); return; }
  if (strg && !e.altKey && (taste === "k" || (e.shiftKey && taste === "p"))) {
    e.preventDefault();
    if (!dialogOffen()) palette();
    return;
  }
  if (strg && !e.altKey && (taste === "z" || taste === "y")) {
    if (imText) return;                         // Text-Undo des Browsers (11)
    e.preventDefault();
    if (ebene) return;                          // bei offenem Dialog/Menü ohne Wirkung
    if (taste === "y" || e.shiftKey) wiederholen(); else rueckgaengig();
    return;
  }
  if (imText || ebene) return;
  if (e.altKey && !strg && /^Digit[1-8]$/.test(e.code)) {
    e.preventDefault();
    const z = NAV_ZIELE[Number(e.code.slice(5)) - 1];
    tid(`nav-${z}`).click();
    return;
  }
  if (strg || e.altKey) return;
  if (e.key === "/") { e.preventDefault(); tid("suche-feld").focus(); return; }
  if (e.key === "?") { e.preventDefault(); tastaturHilfe(); }
});

// ------------------------------------------------------------------ Offline (18)
const offlineHinweis = tid("offline-hinweis");

function offlineSetzen(ja) {
  if (ja === offline) return;
  offline = ja;
  offlineHinweis.hidden = !ja;
  if (ja) {
    // keine veralteten Daten zeigen
    if (aktuell && aktuell.el) {
      const leer = h("section", { class: `seite seite-${aktuell.name}`, tid: `seite-${aktuell.name}`, "data-geladen": "nein" },
        h("h1", null, titelVon(aktuell.name)));
      haupt.replaceChildren(leer);
      tabs.alleVerwerfen();
      Object.assign(aktuell, { el: leer, seite: null, geladen: false });
    }
  }
}
beiOffline(() => offlineSetzen(true));
window.addEventListener("offline", () => offlineSetzen(true));
window.addEventListener("online", async () => {
  offlineSetzen(false);
  try { if (!anmeldung.geladen) await anmeldungLaden(); } catch (e) { behandeln(e); return; }
  await zeigen();
  await benachrichtigungenZaehlen();
});

// ------------------------------------------------------------------ Start
async function start() {
  stapelAnzeigen();
  if (!navigator.onLine) offlineSetzen(true);
  try { await anmeldungLaden(); } catch (e) { behandeln(e); }
  await zeigen();
  app.dataset.bereit = "ja";
  benachrichtigungenZaehlen();
  setInterval(benachrichtigungenZaehlen, 60000);
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => { /* ohne Service Worker weiter */ });
  }
}

window.addEventListener("unhandledrejection", (e) => {
  // Sicherheitsnetz: keine unbehandelten Ablehnungen (1 Nr. 7); Fehler als Meldung zeigen
  e.preventDefault();
  behandeln(e.reason);
});

start();

export { ebenen };
