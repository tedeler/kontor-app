// Änderungsprotokoll (oberflaeche.md 13.9, 25.1, 41.8; Gestaltung D-294): die Seite /protokoll mit Änderungen nach
// Tagen, Quelle als farbige Marke, Filter nach Quelle, Rückgängig je Zeile und „Bis hierher“; dazu das Fenster mit
// den Einzelheiten einer Änderung (D-237: je Objekt vorher → nachher). Alle Texte aus dem Buchbestand laufen über
// h()/textContent.
import { api, betragText, datumText, h, kontoNach, kontoPfad, melde, oberflaeche, stamm, zeitText } from "./kern.js";
import { bestaetigen, dialog, knopf, knopfLeiste } from "./ui.js";

const OBJEKT_NAMEN = { konto: ["Konto", "Konten"], empfaenger: ["Empfänger", "Empfänger"], tag: ["Tag", "Tags"],
  buchung: ["Buchung", "Buchungen"], regel: ["Regel", "Regeln"], verdacht: ["Dublettenverdacht", "Dublettenverdachte"],
  abstimmung: ["Abstimmung", "Abstimmungen"], vorlage: ["Split-Vorlage", "Split-Vorlagen"], kredit: ["Kredit", "Kredite"],
  postfach: ["Postfach", "Postfächer"], dokument: ["Dokument", "Dokumente"], erwartung: ["Erwartete Zahlung", "Erwartete Zahlungen"] };
const ART_TEXT = { angelegt: "angelegt", geaendert: "geändert", geloescht: "gelöscht" };
/** Quelle → [Bezeichnung, Farbton]. Die Farbtöne folgen den Gruppen der Navigation. */
export const QUELLEN = { manuell: ["Von Hand", "hand"], sync: ["Bankabruf", "bank"], umbuchung: ["Umbuchung", "bank"],
  regeln: ["Regel", "auto"], lernmodell: ["Lernmodell", "auto"], vorlage: ["Split-Vorlage", "auto"], kredit: ["Kredit", "auto"],
  mail: ["Mail", "mail"], import: ["Import", "daten"], sicherung: ["Sicherung", "daten"], rueckgaengig: ["Rückgängig", "zurueck"] };
/** Filter der Seite: Name → [Beschriftung, Quellen]; leere Liste = alle. */
const FILTER = [["alle", "Alle", []], ["hand", "Von Hand", ["manuell"]], ["bank", "Bankabruf", ["sync", "umbuchung"]],
  ["automatik", "Automatik", ["regeln", "lernmodell", "vorlage", "kredit", "mail"]],
  ["daten", "Import & Sicherung", ["import", "sicherung"]], ["rueckgaengig", "Rückgängig", ["rueckgaengig"]]];
const FELD_NAMEN = { datum: "Datum", empfaenger_id: "Empfänger", verwendungszweck: "Verwendungszweck", status: "Status", splits: "Aufteilung",
  tag_ids: "Tags", extern_ids: "Kennungen der Herkunft", extern_id: "Kennung der Herkunft", vorschlag: "Vorschlag", gegen_iban: "Gegen-IBAN",
  name: "Name", aliase: "Aliase", standardkategorie_id: "Standardkategorie", eltern_id: "Übergeordnetes Konto", art: "Art", inhaber: "Kontoinhaber",
  konto_id: "Konto", kategorie_id: "Kategorie", betrag: "Betrag", memo: "Notiz", abstimmung_id: "Abstimmung", dokument_ids: "Dokumente",
  buchung_ids: "Buchungen", iban: "IBAN", waehrung: "Währung", bedingungen: "Bedingungen", aktionen: "Aktionen", aktiv: "Aktiv",
  position: "Reihenfolge", automatisch: "Automatisch anwenden", wiederkehrend: "Wiederkehrend", stichtag: "Stichtag", saldo: "Saldo",
  adresse: "Adresse", dateiname: "Dateiname", typ: "Typ", groesse: "Größe", zustand: "Zustand", anbieter: "Anbieter", grund: "Grund",
  kandidaten: "Mögliche Gegenstücke", erstellt_am: "Erstellt am", faellig: "Fällig", frist: "Frist", herkunft: "Herkunft", versteckt: "Versteckt",
  wiederholung: "Wiederholung", rhythmus: "Rhythmus", bis: "Bis", vorgaenger_id: "Folge von", haendler: "Händler / Zahlungsempfänger",
  richtung: "Richtung", beschreibung: "Beschreibung", kennung: "Kennung", gesamt: "Gesamtbetrag", guthaben: "Guthaben", mails: "Mails" };
/** Gespeicherte Kurzwerte in der Schreibweise der Oberfläche. */
const WERTE = { jaehrlich: "jährlich", halbjaehrlich: "halbjährlich", vierteljaehrlich: "vierteljährlich", monatlich: "monatlich",
  woechentlich: "wöchentlich", vorlaeufig: "vorläufig", bestaetigt: "bestätigt", importiert: "importiert", abgeglichen: "abgeglichen",
  eingang: "Eingang", ausgabe: "Ausgabe", offen: "offen", erledigt: "erledigt", geschlossen: "geschlossen", manuell: "von Hand",
  girokonto: "Girokonto", sparkonto: "Sparkonto", kreditkonto: "Kreditkonto", aufwand: "Ausgabe", ertrag: "Einnahme",
  eigenkapital: "Eigenkapital", kreditkarte: "Kreditkarte", bargeld: "Bargeld", depot: "Depot" };
const GRENZE = 50;           // so viele Objekte zeigt das Fenster zunächst; weitere auf Knopfdruck
const gleich = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const istLeer = (w) => w === null || w === undefined || w === "" || (Array.isArray(w) && !w.length);
const zwei = (n) => String(n).padStart(2, "0");

function feldName(schluessel) {
  return FELD_NAMEN[schluessel] || schluessel.replace(/_ids?$/, "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** Farbige Marke der Quelle einer Änderung. */
export function quelleEl(quelle) {
  const [text, ton] = QUELLEN[quelle] || [quelle, "zurueck"];
  return h("span", { class: `pr-quelle pr-ton-${ton}`, "data-quelle": quelle }, text);
}

/** Beschreibung ohne den Zähler „(n Objekte)“; ältere Einträge ohne Beschreibung lesbar machen. */
const ALTE_TITEL = { sync_saldoausgleich: "Synchronisation: Kontostand an die Bank angeglichen" };

export function titelText(a) {
  const t = (a.beschreibung || "").replace(/\s*\(\d+ Objekte?\)$/, "");
  if (ALTE_TITEL[t]) return ALTE_TITEL[t];
  if (/^[a-z_]+$/.test(t)) return t.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  return t || a.aktion;
}

/** Namen zu Kennungen: zuerst aus dem aktuellen Stamm, sonst aus den Zuständen derselben Änderung (gelöschte Objekte). */
function nachschlag(a) {
  const aus = { konto: new Map(), empfaenger: new Map(), tag: new Map() };
  for (const e of a.eintraege) {
    const z = e.nachher || e.vorher;
    if (aus[e.objekt] && z && z.name) aus[e.objekt].set(e.objekt_id, z.name);
  }
  return {
    konto: (id) => { const k = kontoNach(id); return k ? kontoPfad(k) : aus.konto.get(id) || `Konto #${id}`; },
    empfaenger: (id) => { const e = stamm.empfaenger.find((x) => x.id === id); return e ? e.name : aus.empfaenger.get(id) || `Empfänger #${id}`; },
    tag: (id) => { const t = stamm.tags.find((x) => x.id === id); return t ? t.name : aus.tag.get(id) || `Tag #${id}`; },
  };
}

/** Ein Wert als lesbarer Text; `schluessel` bestimmt die Deutung (Betrag in Cent, Kennung eines Kontos …). */
function wertText(schluessel, w, n) {
  if (istLeer(w)) return "–";
  if (typeof w === "boolean") return w ? "ja" : "nein";
  if (/(^|_)(konto|kategorie|eltern|gegenkonto|zielkonto)_id$/.test(schluessel) || schluessel === "eltern_id") return n.konto(w);
  if (schluessel === "empfaenger_id") return n.empfaenger(w);
  if (schluessel === "tag_ids") return w.map((id) => n.tag(id)).join(", ");
  if (typeof w === "number" && /betrag|saldo|summe|rate|zins_cent|gesamt|guthaben|restschuld/.test(schluessel)) return betragText(w);
  if (typeof w === "string" && /^\d{4}-\d{2}-\d{2}$/.test(w)) return datumText(w);
  if (typeof w === "string" && /^\d{4}-\d{2}-\d{2}T/.test(w)) return zeitText(w);
  if (typeof w === "string" && Object.hasOwn(WERTE, w)) return WERTE[w];
  if (schluessel === "inhaber") return [w.vorname, w.nachname].filter(Boolean).join(" ") || "–";   // D-310
  if (schluessel === "splits") return w.map((s) => splitText(s, n)).join("\n");
  if (Array.isArray(w)) return w.map((x) => (typeof x === "object" && x !== null ? objektText(x, n) : wertText(schluessel.replace(/s$/, ""), x, n))).join("\n");
  if (typeof w === "object") return objektText(w, n);
  return String(w);
}

function splitText(s, n) {
  return `${n.konto(s.konto_id)}: ${betragText(s.betrag)}${s.memo ? ` (${s.memo})` : ""}${s.abstimmung_id ? " · abgestimmt" : ""}`;
}

function objektText(o, n) {
  return Object.entries(o).filter(([k, v]) => k !== "id" && !istLeer(v)).map(([k, v]) => `${feldName(k)}: ${wertText(k, v, n)}`).join(" · ") || "–";
}

/** Kurze Bezeichnung des Objekts für die Überschrift seines Abschnitts. */
function objektTitel(e, n) {
  const z = e.nachher || e.vorher || {};
  if (e.objekt === "buchung") {
    const betrag = (z.splits || []).filter((s) => s.betrag > 0).reduce((x, s) => x + s.betrag, 0);
    return [z.datum ? datumText(z.datum) : null, z.empfaenger_id ? n.empfaenger(z.empfaenger_id) : null,
      z.verwendungszweck || null, z.splits ? betragText(betrag) : null].filter(Boolean).join(" · ") || `#${e.objekt_id}`;
  }
  if (e.objekt === "konto" && z.name) return n.konto(e.objekt_id) === `Konto #${e.objekt_id}` ? z.name : n.konto(e.objekt_id);
  if (e.objekt === "erwartung") return [z.haendler, z.beschreibung].filter(Boolean).join(" · ") || `#${e.objekt_id}`;
  if (e.objekt === "abstimmung" && z.stichtag) return [z.konto_id ? n.konto(z.konto_id) : null, `zum ${datumText(z.stichtag)}`].filter(Boolean).join(" ");
  return z.name || z.adresse || z.dateiname || `#${e.objekt_id}`;
}

/** Zeilen (Feld, vorher, nachher) eines Eintrags: bei „geändert“ nur die abweichenden Angaben, sonst alle nicht leeren. */
export function unterschiede(e) {
  const v = e.vorher || {};
  const nn = e.nachher || {};
  const schluessel = [...new Set([...Object.keys(v), ...Object.keys(nn)])].filter((k) => k !== "id");
  if (e.art === "geaendert") return schluessel.filter((k) => !gleich(v[k], nn[k])).map((k) => [k, v[k], nn[k]]);
  const z = e.art === "angelegt" ? nn : v;
  return schluessel.filter((k) => !istLeer(z[k])).map((k) => [k, v[k], nn[k]]);
}

function eintragEl(e, n) {
  const namen = OBJEKT_NAMEN[e.objekt] || [e.objekt, e.objekt];
  const zeilen = unterschiede(e);
  const kopfZeile = e.art === "geaendert" ? ["Angabe", "Vorher", "Nachher"] : ["Angabe", e.art === "angelegt" ? "Wert" : "Wert vor dem Löschen"];
  const zelle = (k, w, klasse) => h("td", { class: klasse }, wertText(k, w, n));
  return h("section", { class: "ae-eintrag", tid: `ae-eintrag-${e.objekt}-${e.objekt_id}`, "data-objekt": e.objekt, "data-art": e.art },
    h("h3", null, h("span", { class: `ae-art ae-${e.art}` }, ART_TEXT[e.art] || e.art),
      h("span", { class: "ae-objekt" }, namen[0]), h("span", { class: "ae-titel" }, objektTitel(e, n)),
      h("small", { class: "ae-nr" }, `#${e.objekt_id}`)),
    zeilen.length ? h("table", { class: "tabelle ae-tabelle" + (e.art === "geaendert" ? " ae-dreispaltig" : "") },
      h("thead", null, h("tr", null, kopfZeile.map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", null, zeilen.map(([k, v, nn]) => h("tr", { "data-feld": k }, h("th", { scope: "row" }, feldName(k)),
        ...(e.art === "geaendert" ? [zelle(k, v, "ae-vorher"), zelle(k, nn, "ae-nachher")] : [zelle(k, e.art === "angelegt" ? nn : v, "")])))))
      : h("p", { class: "klein" }, "Keine abweichenden Angaben."));
}

/** „3 Buchungen geändert, 1 Tag angelegt“ */
export function zusammenfassung(eintraege) {
  const zahl = new Map();
  for (const e of eintraege) zahl.set(`${e.objekt}|${e.art}`, (zahl.get(`${e.objekt}|${e.art}`) || 0) + 1);
  return [...zahl].map(([k, anzahl]) => {
    const [objekt, art] = k.split("|");
    const namen = OBJEKT_NAMEN[objekt] || [objekt, objekt];
    return `${anzahl} ${namen[anzahl === 1 ? 0 : 1]} ${ART_TEXT[art] || art}`;
  }).join(", ");
}

/** Zweite Zeile eines Eintrags der Liste: bei einem Objekt dessen Bezeichnung, sonst der Umfang. */
function unterzeile(a) {
  if (a.eintraege.length === 1) {
    const e = a.eintraege[0];
    return `${(OBJEKT_NAMEN[e.objekt] || [e.objekt])[0]}: ${objektTitel(e, nachschlag(a))}`;
  }
  return zusammenfassung(a.eintraege) || "keine Objekte";
}

/** Öffnet das Fenster mit den Einzelheiten der Änderung `id`. */
export async function aenderungFenster(id, ausloeser) {
  const a = await api("GET", `/api/aenderungen/${id}`);
  const n = nachschlag(a);
  return dialog("aenderung-dialog", titelText(a), (inhalt, d) => {
    const wirksam = a.rueckgaengig_durch === null;
    const angabe = (titel, wert, attrs) => h("div", { class: "ae-angabe" }, h("dt", null, titel), h("dd", attrs || null, wert));
    const kopf = h("dl", { class: "ae-kopf" },
      angabe("Zeitpunkt", zeitText(a.zeitpunkt)),
      angabe("Quelle", quelleEl(a.quelle)),
      angabe("Umfang", zusammenfassung(a.eintraege), { tid: "ae-umfang" }),
      angabe("Stand", wirksam ? "wirksam" : `rückgängig gemacht durch Änderung #${a.rueckgaengig_durch}`,
        { tid: "ae-stand", class: wirksam ? "ae-wirksam" : "ae-zurueck" }),
      ...(a.rueckgaengig_von.length ? [angabe("Macht rückgängig", a.rueckgaengig_von.map((x) => `#${x}`).join(", "))] : []),
      angabe("Änderung", h("span", null, `#${a.id} · `, h("code", { tid: "ae-aktion" }, a.aktion))));
    const suche = h("input", { type: "search", tid: "ae-suche", class: "listen-suche", placeholder: "In den Einzelheiten suchen …",
      "aria-label": "Einzelheiten durchsuchen", maxlength: "200", hidden: a.eintraege.length < 6 });
    const liste = h("div", { class: "ae-liste", tid: "ae-liste" });
    const mehr = knopf("Weitere anzeigen", { tid: "ae-mehr", hidden: true });
    const stand = h("p", { class: "klein", tid: "ae-anzahl", "aria-live": "polite" });
    let gezeigt = GRENZE;
    let texte = null;         // Suchtext je Eintrag, erst bei der ersten Suche gebildet
    const zeigen = () => {
      const w = suche.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
      let treffer = a.eintraege;
      if (w.length) {
        if (!texte) texte = a.eintraege.map((e) => `${objektTitel(e, n)} ${unterschiede(e).map(([k, v, nn]) => `${feldName(k)} ${wertText(k, v, n)} ${wertText(k, nn, n)}`).join(" ")}`.toLowerCase());
        treffer = a.eintraege.filter((_e, i) => w.every((x) => texte[i].includes(x)));
      }
      liste.replaceChildren(...treffer.slice(0, gezeigt).map((e) => eintragEl(e, n)));
      mehr.hidden = treffer.length <= gezeigt;
      mehr.textContent = `Weitere ${Math.min(GRENZE, treffer.length - gezeigt)} anzeigen`;
      stand.textContent = treffer.length === a.eintraege.length
        ? (treffer.length > gezeigt ? `${gezeigt} von ${treffer.length} Objekten angezeigt` : "")
        : `${treffer.length} von ${a.eintraege.length} Objekten passen`;
    };
    suche.addEventListener("input", () => { gezeigt = GRENZE; zeigen(); });
    mehr.addEventListener("click", () => { gezeigt += GRENZE; zeigen(); });
    zeigen();
    inhalt.append(kopf, suche, stand, liste, knopfLeiste(mehr, knopf("Schließen", { tid: "ae-schliessen", onclick: () => d.schliessen(null) })));
  }, { ausloeser, klasse: "dialog-breit dialog-aenderung", schliessenKnopf: "aenderung-dialog-zu" });
}

// ------------------------------------------------------------------ Seite /protokoll

function tagSchluessel(wert) {
  const d = new Date(wert);
  return `${d.getFullYear()}-${zwei(d.getMonth() + 1)}-${zwei(d.getDate())}`;
}

/** „Heute“, „Gestern“ oder „Montag, 23. November“ (mit Jahr, wenn es nicht das laufende ist). */
function tagText(schluessel) {
  const jetzt = new Date();
  const gestern = new Date(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate() - 1);
  if (schluessel === tagSchluessel(jetzt)) return "Heute";
  if (schluessel === tagSchluessel(gestern)) return "Gestern";
  const [j, m, t] = schluessel.split("-").map(Number);
  return new Date(j, m - 1, t).toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long",
    ...(j === jetzt.getFullYear() ? {} : { year: "numeric" }) });
}

function uhrzeit(wert) {
  const d = new Date(wert);
  return `${zwei(d.getHours())}:${zwei(d.getMinutes())}`;
}

const anzahlText = (n) => (n === 1 ? "1 Änderung" : `${n.toLocaleString("de-DE")} Änderungen`);

export async function protokollSeite(seite) {
  const filterLeiste = h("div", { class: "pr-filter", role: "group", "aria-label": "Nach Quelle filtern", tid: "protokoll-filter" });
  const stand = h("p", { class: "pr-stand", tid: "protokoll-stand", "aria-live": "polite" });
  const liste = h("div", { class: "pr-liste", tid: "protokoll-liste" });
  const leerEl = h("p", { class: "leer pr-leer", hidden: true });
  const mehr = knopf("Ältere laden", { tid: "protokoll-mehr", class: "knopf pr-mehr", hidden: true });
  const aelter = h("p", { class: "klein pr-aelter", tid: "protokoll-aelter" }, "Ältere Änderungen stehen in den ",
    h("a", { href: "/sicherung" }, "Sicherungspunkten"), ".");
  seite.classList.add("seite-protokoll");
  seite.append(h("div", { class: "seiten-kopf pr-kopf" }, h("div", null, h("h1", null, "Änderungsprotokoll"), stand)),
    filterLeiste, liste, leerEl, mehr, aelter);

  let filter = FILTER[0];
  let seiteNr = 0;
  let geladen = [];
  let gesamt = 0;
  let abruf = 0;             // nur die Antwort des jüngsten Abrufs zählt (schnelles Umschalten der Filter)

  async function laden(n) {
    const q = new URLSearchParams({ pro_seite: "50", seite: String(n) });
    for (const x of filter[2]) q.append("quelle", x);
    return api("GET", `/api/aenderungen?${q}`);
  }

  // Rückgängig bis hierher (D-108, 25.1): alle Änderungen ab dieser (einschließlich) in einem Schritt. Nur ohne Filter:
  // sonst würden auch ausgeblendete Änderungen zurückgenommen.
  function markieren(id) {
    for (const li of liste.querySelectorAll("li.aenderung")) li.classList.toggle("bis-markiert", id !== null && Number(li.dataset.id) >= id);
  }
  function bisKnopf(a) {
    if (filter[2].length) return null;
    const neuer = geladen.filter((x) => x.id >= a.id && x.rueckgaengig_durch === null).length;
    if (!neuer) return null;
    const k = knopf("Bis hierher", { tid: `aenderung-bis-${a.id}`, class: "knopf pr-aktion",
      title: "Diese und alle neueren Änderungen rückgängig machen",
      "aria-label": `Alle Änderungen bis einschließlich ${a.id} rückgängig machen`, onclick: async () => {
        markieren(a.id);
        const ok = await bestaetigen(`Alle Änderungen seit „${titelText(a)}“ (${zeitText(a.zeitpunkt)}) einschließlich `
          + "dieser rückgängig machen? Das ergibt eine einzige neue Änderung, die sich ebenfalls wieder rückgängig machen lässt.",
        { ja: "Bis hierher rückgängig", ausloeser: k });
        markieren(null);
        if (!ok) return;
        try {
          const u = await api("POST", "/api/aenderungen/rueckgaengig", { bis_id: a.id });
          melde("erfolg", `${u.rueckgaengig_von.length === 1 ? "1 Änderung" : `${u.rueckgaengig_von.length} Änderungen`} rückgängig gemacht.`);
          await oberflaeche.neuLaden();
        } catch (e) { melde("fehler", e.message); }
      } });
    k.prepend(h("span", { class: "pr-symbol", "aria-hidden": "true" }, "⤒"));
    k.addEventListener("mouseenter", () => markieren(a.id));
    k.addEventListener("mouseleave", () => markieren(null));
    k.addEventListener("focus", () => markieren(a.id));
    k.addEventListener("blur", () => markieren(null));
    return k;
  }

  function zeileEl(a) {
    const wirksam = a.rueckgaengig_durch === null;       // protokoll.md 3
    const titel = titelText(a);
    const zusatz = [];
    if (!wirksam) zusatz.push(h("span", { class: "pr-hinweis pr-hinweis-zurueck" }, `zurückgenommen durch #${a.rueckgaengig_durch}`));
    if (a.rueckgaengig_von.length) {
      zusatz.push(h("span", { class: "pr-hinweis" }, `nimmt ${a.rueckgaengig_von.length === 1 ? "Änderung" : "Änderungen"} `
        + `${a.rueckgaengig_von.slice(0, 3).map((x) => `#${x}`).join(", ")}${a.rueckgaengig_von.length > 3 ? " …" : ""} zurück`));
    }
    const rueck = wirksam ? knopf("Rückgängig", { tid: `aenderung-rueckgaengig-${a.id}`, class: "knopf pr-aktion",
      "aria-label": `Änderung ${a.id} rückgängig machen`, onclick: async () => {
        try { await api("POST", `/api/aenderungen/${a.id}/rueckgaengig`); melde("erfolg", "Rückgängig gemacht."); await oberflaeche.neuLaden(); }
        catch (e) { melde("fehler", e.message); }
      } }) : null;
    if (rueck) rueck.prepend(h("span", { class: "pr-symbol", "aria-hidden": "true" }, "↶"));
    return h("li", { tid: `aenderung-${a.id}`, "data-id": String(a.id), "data-quelle": a.quelle,
      "data-wirksam": wirksam ? "ja" : "nein", class: "aenderung pr-zeile" + (wirksam ? "" : " unwirksam") },
    h("time", { class: "pr-zeit", datetime: a.zeitpunkt, "data-zeitpunkt": a.zeitpunkt, title: zeitText(a.zeitpunkt) }, uhrzeit(a.zeitpunkt)),
    quelleEl(a.quelle),
    h("div", { class: "pr-inhalt" },
      // D-237: Einzelheiten der Änderung (je Objekt vorher → nachher) in einem eigenen Fenster; die Beschreibung öffnet es
      h("button", { type: "button", class: "pr-titel", tid: `aenderung-einzelheiten-${a.id}`, "aria-haspopup": "dialog",
        "aria-label": `Einzelheiten der Änderung ${a.id}: ${titel}`, title: "Einzelheiten zeigen",
        onclick: (ev) => aenderungFenster(a.id, ev.currentTarget).catch((e) => melde("fehler", e.message)) }, titel),
      h("div", { class: "pr-unter" }, h("span", { class: "pr-umfang" }, unterzeile(a)), ...zusatz)),
    h("div", { class: "pr-aktionen" }, rueck, bisKnopf(a)));
  }

  function zeichnen() {
    const tage = new Map();
    for (const a of geladen) {
      const s = tagSchluessel(a.zeitpunkt);
      if (!tage.has(s)) tage.set(s, []);
      tage.get(s).push(a);
    }
    liste.replaceChildren(...[...tage].map(([s, eintraege]) => h("section", { class: "pr-tag", "data-tag": s },
      h("h2", { class: "pr-tag-titel" }, h("span", null, tagText(s)),
        h("span", { class: "pr-tag-zahl" }, anzahlText(eintraege.length))),
      h("ol", { class: "pr-tag-liste" }, eintraege.map(zeileEl)))));
    const name = filter[2].length ? ` · ${filter[1]}` : "";
    stand.textContent = gesamt ? `${anzahlText(gesamt)}${name}` : "";
    leerEl.hidden = geladen.length > 0;
    leerEl.textContent = filter[2].length ? `Keine Änderungen in „${filter[1]}“.` : "Noch keine Änderungen.";
    mehr.hidden = geladen.length >= gesamt;
    // D-302: Das Protokoll reicht nur rund eine Stunde zurück; ältere Stände stehen in den Sicherungspunkten
    aelter.hidden = geladen.length < gesamt;
    mehr.textContent = `Ältere laden (${geladen.length.toLocaleString("de-DE")} von ${gesamt.toLocaleString("de-DE")} angezeigt)`;
  }

  async function neu() {
    const nr = ++abruf;
    const s = await laden(1);
    if (nr !== abruf) return;
    seiteNr = 1;
    geladen = s.eintraege;
    gesamt = s.gesamt;
    zeichnen();
  }

  filterLeiste.append(...FILTER.map((f) => {
    const k = h("button", { type: "button", class: "chip" + (f === filter ? " an" : ""), tid: `protokoll-filter-${f[0]}`,
      "aria-pressed": f === filter ? "true" : "false" }, f[1]);
    k.addEventListener("click", () => {
      if (filter === f) return;
      filter = f;
      for (const b of filterLeiste.children) {
        const an = b === k;
        b.classList.toggle("an", an);
        b.setAttribute("aria-pressed", an ? "true" : "false");
      }
      neu().catch((e) => melde("fehler", e.message));
    });
    return k;
  }));
  mehr.addEventListener("click", async () => {
    const nr = abruf;
    const s = await laden(seiteNr + 1);
    if (nr !== abruf) return;
    seiteNr += 1;
    geladen = geladen.concat(s.eintraege);
    gesamt = s.gesamt;
    zeichnen();
  });
  await neu();
  return { titel: "Änderungsprotokoll" };
}
