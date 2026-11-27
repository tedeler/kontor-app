// Sicherungspunkte (D-302, sicherungspunkte.md, oberflaeche.md 49): Seite /sicherung mit aktuellem Stand, Speicher,
// Zeitleiste der Punkte nach Tagen (ältere nach Wochen und Monaten, eingeklappt) und dem Fenster eines Punkts
// (Unterschied zum aktuellen Stand, Chronik, Wechseln, Herunterladen, Anheften, Benennen). Alle Texte laufen über
// h()/textContent.
import { aktion, api, h, melde, zeitText } from "./kern.js";
import { bestaetigen, dialog, feld, imDialog, knopf, knopfLeiste } from "./ui.js";
import { quelleEl, titelText } from "./aenderung.js";

const MARKEN = { stuendlich: ["Stündlich", "zurueck"], von_hand: ["Von Hand", "hand"],
  vor_wiederherstellung: ["Vor Wechsel", "auto"], aus_datei: ["Aus Datei", "daten"], vor_update: ["Vor Update", "bank"] };
const OBJEKTE = { konto: ["Konto", "Konten"], empfaenger: ["Empfänger", "Empfänger"], tag: ["Tag", "Tags"],
  buchung: ["Buchung", "Buchungen"], regel: ["Regel", "Regeln"], verdacht: ["Dublettenverdacht", "Dublettenverdachte"],
  abstimmung: ["Abstimmung", "Abstimmungen"], vorlage: ["Split-Vorlage", "Split-Vorlagen"], kredit: ["Kredit", "Kredite"],
  postfach: ["Postfach", "Postfächer"], dokument: ["Beleg", "Belege"], erwartung: ["Geplante Zahlung", "Geplante Zahlungen"] };
// Tabellen der Sicherung → Objektart der Zusammenfassung (Splits, Tags an Buchungen … zählen zur Buchung)
const TABELLE_OBJEKT = { konto: "konto", empfaenger: "empfaenger", empfaenger_alias: "empfaenger", tag: "tag",
  buchung: "buchung", split: "buchung", buchung_tag: "buchung", vorschlag: "buchung", regel: "regel",
  dublettenverdacht: "verdacht", abstimmung: "abstimmung", vorlage: "vorlage", kredit: "kredit", postfach: "postfach",
  dokument: "dokument", erwartung: "erwartung", einstellung: "einstellung" };
const STUFEN = [["stunden", "Stunden"], ["tage", "Tage"], ["wochen", "Wochen"], ["monate", "Monate"],
  ["angeheftet", "Angeheftet"], ["basis", "Grundlage"]];
const zwei = (n) => String(n).padStart(2, "0");

export function groesseText(bytes) {
  if (bytes === null || bytes === undefined) return "–";
  if (bytes < 1024) return `${bytes} B`;
  const einheiten = ["KB", "MB", "GB", "TB"];
  let w = bytes / 1024;
  let i = 0;
  while (w >= 1024 && i < einheiten.length - 1) { w /= 1024; i += 1; }
  return `${w.toLocaleString("de-DE", { maximumFractionDigits: w < 10 ? 1 : 0 })} ${einheiten[i]}`;
}

function datum(wert) { return new Date(wert); }
function uhrzeit(wert) { const d = datum(wert); return `${zwei(d.getHours())}:${zwei(d.getMinutes())}`; }
function tagSchluessel(wert) { const d = datum(wert); return `${d.getFullYear()}-${zwei(d.getMonth() + 1)}-${zwei(d.getDate())}`; }

function tagText(schluessel, jetzt) {
  const gestern = new Date(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate() - 1);
  if (schluessel === tagSchluessel(jetzt)) return "Heute";
  if (schluessel === tagSchluessel(gestern)) return "Gestern";
  const [j, m, t] = schluessel.split("-").map(Number);
  return new Date(j, m - 1, t).toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long",
    ...(j === jetzt.getFullYear() ? {} : { year: "numeric" }) });
}

/** Bezeichnung eines Punkts für Rückfragen und Meldungen: „Do 26.11., 14:00“. */
export function punktText(p) {
  const d = datum(p.zeitpunkt);
  const tag = d.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
  return `${tag}, ${uhrzeit(p.zeitpunkt)}${p.name ? ` („${p.name}“)` : ""}`;
}

function markeEl(m) {
  const [text, ton] = MARKEN[m] || [m, "zurueck"];
  return h("span", { class: `pr-quelle pr-ton-${ton}`, "data-marke": m }, text);
}

/** „12 Buchungen neu, 3 Regeln geändert“ aus den Zählungen je Tabelle. */
export function aenderungenText(aenderungen) {
  const je = new Map();
  for (const [t, z] of Object.entries(aenderungen || {})) {
    const o = TABELLE_OBJEKT[t];
    if (!o) continue;
    if (t !== o && !(t === "dublettenverdacht" && o === "verdacht")) continue;   // Splits, Zuordnungen: nur im Hinweis unten
    const a = je.get(o) || { neu: 0, geaendert: 0, geloescht: 0 };
    a.neu += z.neu; a.geloescht += z.geloescht; a.geaendert += z.geaendert;
    je.set(o, a);
  }
  const teile = [];
  for (const [o, a] of je) {
    if (o === "einstellung") { if (a.neu + a.geaendert + a.geloescht) teile.push("Einstellungen geändert"); continue; }
    const [eins, viele] = OBJEKTE[o];
    const n = (k) => `${k} ${k === 1 ? eins : viele}`;
    if (a.neu) teile.push(`${n(a.neu)} neu`);
    if (a.geaendert) teile.push(`${n(a.geaendert)} geändert`);
    if (a.geloescht) teile.push(`${n(a.geloescht)} gelöscht`);
  }
  const buchungTeile = ["split", "buchung_tag", "vorschlag"].some((t) => (aenderungen || {})[t]);
  if (buchungTeile && !(je.get("buchung") || {}).geaendert) teile.push("Kategorien, Aufteilungen oder Tags geändert");
  if (!teile.length && Object.keys(aenderungen || {}).length) teile.push("Kleinere Änderungen (Zuordnungen, Kennungen)");
  return teile.join(", ");
}

/** Wirkung eines Wechsels aus dem Probelauf: angelegt = kommt zurück, gelöscht = entfällt. */
export function wirkungText(unterschied) {
  const teile = [];
  for (const [o, z] of Object.entries(unterschied || {})) {
    const [eins, viele] = OBJEKTE[o] || [o, o];
    const n = (k) => `${k} ${k === 1 ? eins : viele}`;
    if (z.geloescht) teile.push(`${n(z.geloescht)} ${z.geloescht === 1 ? "entfällt" : "entfallen"}`);
    if (z.angelegt) teile.push(`${n(z.angelegt)} ${z.angelegt === 1 ? "kommt" : "kommen"} zurück`);
    if (z.geaendert) teile.push(`${n(z.geaendert)} ${z.geaendert === 1 ? "wird" : "werden"} zurückgesetzt`);
  }
  return teile.length ? teile.join(", ") : "Keine Unterschiede im Buchbestand.";
}

// ------------------------------------------------------------------ Fenster eines Punkts

/** D-314: Das Fenster öffnet sofort mit den Angaben aus der Liste; Unterschied und Chronik kommen nach. */
function punktFenster(p, ausloeser, neuLaden) {
  let vergleich = null;   // bis zur Antwort unbekannt: Wechseln bleibt gesperrt
  const wirkung = h("p", { tid: "punkt-wirkung", "data-geladen": "nein", class: "klein", "aria-live": "polite" },
    p.aktuell ? "Entspricht dem aktuellen Stand." : "Unterschied zum aktuellen Stand wird ermittelt …");
  const bank = h("p", { class: "klein", hidden: true },
    "Entfallende Bankumsätze kommen beim nächsten Abruf wieder, solange die Bank sie noch liefert.");
  const chronikPlatz = h("div", null, h("p", { class: "leer", tid: "punkt-chronik", "data-geladen": "nein" }, "Wird geladen …"));
  const wechseln = knopf("Auf diesen Stand wechseln", { tid: "punkt-wechseln", class: "knopf knopf-haupt", disabled: true });
  const d = dialog("punkt-dialog", `Sicherungspunkt ${punktText(p)}`, (inhalt, dd) => {
    const angaben = h("dl", { class: "sp-angaben", tid: "punkt-angaben" },
      h("dt", null, "Eigene Größe"), h("dd", null, groesseText(p.groesse)),
      h("dt", null, "Zum Herstellen"), h("dd", null, groesseText(p.groesse_herstellen)),
      h("dt", null, "Art"), h("dd", null, p.anker ? "vollständige Sicherung (Anker)" : "Änderungen gegenüber dem vorigen Punkt"),
      h("dt", null, "Geprüft"), h("dd", null, p.geprueft_am ? zeitText(p.geprueft_am) : "noch nicht"),
      h("dt", null, "Änderungen"), h("dd", null, aenderungenText(p.aenderungen) || "–"));
    wechseln.addEventListener("click", async (e) => {
      if (!vergleich || vergleich.fehler) return;
      const ok = await bestaetigen(`Der aktuelle Stand wird vorher gesichert, danach werden alle Daten durch den Stand `
        + `vom ${punktText(p)} ersetzt. ${vergleich.unterschied ? wirkungText(vergleich.unterschied) + " " : ""}`
        + "Zugangsdaten und Anmeldung bleiben. Sie können jederzeit zurück.", { ja: "Stand wechseln", ausloeser: e.currentTarget });
      if (!ok) return;
      melde("info", "Stand wird gewechselt …");
      await imDialog(dd, wechseln, () => aktion(() => api("POST", `/api/sicherung/punkte/${p.kennung}/wechseln?bestaetigt=true`),
        { stillBeiFehler: true, danach: () => dd.schliessen(true), erfolg: `Stand vom ${punktText(p)} hergestellt.` }));
      await neuLaden();
    });
    const laden = h("a", { class: "knopf", tid: "punkt-herunterladen", href: `/api/sicherung/punkte/${p.kennung}/datei`,
      download: "" }, "Herunterladen");
    const anheften = knopf(p.angeheftet ? "Lösen" : "Anheften", { tid: "punkt-anheften", onclick: () => imDialog(dd, anheften,
      async () => { await api("PATCH", `/api/sicherung/punkte/${p.kennung}`, { angeheftet: !p.angeheftet }); dd.schliessen(true); await neuLaden(); }) });
    const name = h("input", { type: "text", value: p.name || "", maxlength: "100", tid: "punkt-name" });
    const benennen = knopf("Speichern", { tid: "punkt-benennen", onclick: () => imDialog(dd, benennen,
      async () => { await api("PATCH", `/api/sicherung/punkte/${p.kennung}`, { name: name.value.trim() || null }); dd.schliessen(true); await neuLaden(); }) });
    inhalt.append(wirkung, bank, angaben, h("h3", null, "Chronik"), chronikPlatz,
      h("div", { class: "sp-name-zeile" }, feld("Name", name), benennen),
      knopfLeiste(wechseln, laden, anheften, knopf("Schließen", { onclick: () => dd.schliessen(null) })));
  }, { ausloeser, klasse: "dialog-breit" });
  api("GET", `/api/sicherung/punkte/${p.kennung}/vergleich`).catch((e) => ({ fehler: e })).then((v) => {
    vergleich = v;
    const gleich = !v.fehler && !v.geaendert;
    wirkung.className = v.fehler ? "fehler" : "";
    if (v.fehler) wirkung.setAttribute("role", "alert");
    wirkung.textContent = v.fehler ? v.fehler.message
      : gleich ? "Entspricht dem aktuellen Stand." : `Wechsel auf diesen Stand: ${wirkungText(v.unterschied)}.`;
    if (!v.fehler) wirkung.dataset.gleich = gleich ? "ja" : "nein";
    wirkung.dataset.geladen = "ja";
    bank.hidden = !(!v.fehler && v.unterschied && v.unterschied.buchung && v.unterschied.buchung.geloescht);
    wechseln.disabled = gleich || Boolean(v.fehler);
  });
  api("GET", `/api/sicherung/punkte/${p.kennung}/chronik`).catch(() => ({ eintraege: [] })).then((chronik) => {
    chronikPlatz.replaceChildren(chronik.eintraege.length
      ? h("ol", { class: "sp-chronik", tid: "punkt-chronik", "data-geladen": "ja" }, chronik.eintraege.slice().reverse().map((e) =>
        h("li", null, h("time", { class: "pr-zeit", datetime: e.zeitpunkt }, uhrzeit(e.zeitpunkt)), quelleEl(e.quelle),
          h("span", null, titelText(e)))))
      : h("p", { class: "leer", tid: "punkt-chronik", "data-geladen": "ja" }, "Keine Einträge (zum Beispiel ein Anker nach dem Einspielen)."));
  });
  return d;
}

// ------------------------------------------------------------------ Seite

function gruppenSchluessel(p, jetzt) {
  const alter = jetzt - datum(p.zeitpunkt);
  const tag = 86400000;
  if (alter <= 30 * tag) return ["tag", tagSchluessel(p.zeitpunkt), tagText(tagSchluessel(p.zeitpunkt), jetzt)];
  const d = datum(p.zeitpunkt);
  const monat = d.toLocaleDateString("de-DE", { month: "long", year: "numeric" });
  return ["monat", `${d.getFullYear()}-${zwei(d.getMonth() + 1)}`, monat];
}

function eineZeile(p, oeffnen) {
  const name = p.name ? h("span", { class: "sp-name" }, p.name) : null;
  const was = aenderungenText(p.aenderungen) || (p.anker ? "vollständige Sicherung" : "–");
  const zusatz = [];
  if (p.aktuell) zusatz.push(h("span", { class: "pr-hinweis sp-jetzt-hinweis" }, "entspricht dem aktuellen Stand"));
  if (p.vorwaerts) zusatz.push(h("span", { class: "pr-hinweis" }, "vorwärts"));
  if (p.verlassen) zusatz.push(h("span", { class: "pr-hinweis" }, "verlassener Verlauf"));
  return h("li", { tid: `punkt-${p.kennung}`, "data-kennung": p.kennung, class: "pr-zeile sp-zeile"
      + (p.aktuell ? " sp-aktuell" : "") + (p.verlassen ? " sp-verlassen" : ""), "data-anker": p.anker ? "ja" : "nein" },
  h("time", { class: "pr-zeit", datetime: p.zeitpunkt, title: zeitText(p.zeitpunkt) }, uhrzeit(p.zeitpunkt)),
  // „Stündlich“ nur, wenn der Punkt keine weitere Marke trägt
  h("span", { class: "sp-marken" }, (p.marken.length > 1 ? p.marken.filter((m) => m !== "stuendlich") : p.marken).map(markeEl)),
  h("div", { class: "pr-inhalt" },
    h("button", { type: "button", class: "pr-titel", tid: `punkt-oeffnen-${p.kennung}`, "aria-haspopup": "dialog",
      onclick: (e) => oeffnen(p, e.currentTarget) }, name || was),
    h("div", { class: "pr-unter" }, name ? h("span", { class: "pr-umfang" }, was) : null,
      h("span", { class: "pr-hinweis sp-groesse", tid: `punkt-groesse-${p.kennung}` }, groesseText(p.groesse)),
      p.geprueft_am ? h("span", { class: "pr-hinweis", title: `geprüft ${zeitText(p.geprueft_am)}` }, "✓ geprüft") : null,
      p.angeheftet ? h("span", { class: "pr-hinweis" }, "📌 angeheftet") : null, ...zusatz)),
  h("div", { class: "pr-aktionen" },
    h("a", { class: "knopf pr-aktion", href: `/api/sicherung/punkte/${p.kennung}/datei`, download: "",
      tid: `punkt-laden-${p.kennung}`, "aria-label": `Sicherungspunkt ${punktText(p)} herunterladen` }, "Herunterladen")));
}

/** Prüfungen ohne Änderung (D-307): aufeinanderfolgende zu einer Zeile zusammengefasst. */
function pruefZeile(gruppe) {
  const neu = gruppe[0].zeitpunkt;
  const alt = gruppe[gruppe.length - 1].zeitpunkt;
  const text = gruppe.length === 1 ? `${uhrzeit(neu)} geprüft – keine Änderung`
    : `${uhrzeit(alt)}–${uhrzeit(neu)} · ${gruppe.length} Prüfungen – keine Änderung`;
  return h("li", { class: "sp-pruefung", tid: `pruefung-${neu}`, "data-anzahl": String(gruppe.length) },
    h("span", { class: "sp-pruefung-zeichen", "aria-hidden": "true" }, "✓"), text);
}

function zeitleiste(punkte, pruefungen, oeffnen, jetzt) {
  // Punkte und Prüfungen ohne Änderung, neueste zuerst
  const eintraege = [...punkte.map((p) => ({ zeitpunkt: p.zeitpunkt, punkt: p })),
    ...pruefungen.map((x) => ({ zeitpunkt: x.zeitpunkt, pruefung: x }))]
    .sort((a, b) => (a.zeitpunkt < b.zeitpunkt ? 1 : a.zeitpunkt > b.zeitpunkt ? -1 : a.punkt ? -1 : 1));
  const gruppen = new Map();
  for (const e of eintraege) {
    const [art, s, text] = gruppenSchluessel(e, jetzt);
    if (!gruppen.has(s)) gruppen.set(s, { art, text, eintraege: [] });
    gruppen.get(s).eintraege.push(e);
  }
  return [...gruppen].map(([s, g]) => {
    const zeilen = [];
    let offen = [];
    const abschliessen = () => { if (offen.length) zeilen.push(pruefZeile(offen)); offen = []; };
    for (const e of g.eintraege) {
      if (e.pruefung) { offen.push(e.pruefung); continue; }
      abschliessen();
      zeilen.push(eineZeile(e.punkt, oeffnen));
    }
    abschliessen();
    const gp = g.eintraege.filter((e) => e.punkt).map((e) => e.punkt);
    const summe = gp.reduce((a, p) => a + p.groesse, 0);
    const zahl = gp.length ? `${gp.length === 1 ? "1 Punkt" : `${gp.length} Punkte`} · ${groesseText(summe)}` : "keine Änderung";
    const kopf = h("h2", { class: "pr-tag-titel" }, h("span", null, g.text), h("span", { class: "pr-tag-zahl" }, zahl));
    const liste = h("ol", { class: "pr-tag-liste" }, zeilen);
    if (g.art === "tag") return h("section", { class: "pr-tag", "data-tag": s }, kopf, liste);
    return h("details", { class: "pr-tag sp-alt", "data-monat": s }, h("summary", null, kopf), liste);
  });
}

function standKachel(st) {
  const bezug = st.punkte.find((p) => p.kennung === st.bezugspunkt);
  let text;
  let zustand;
  if (!bezug) { text = st.zuletzt_geprueft ? "Noch kein Sicherungspunkt." : "Die stündliche Sicherung ist noch nicht gelaufen."; zustand = "offen"; }
  else if (st.unveraendert) { text = `Gesichert · unverändert seit ${punktText(bezug)}`; zustand = "ok"; }
  else { text = `Ungesicherte Änderungen seit ${punktText(bezug)} · nächste Sicherung ${uhrzeit(st.naechster_lauf)}`; zustand = "offen"; }
  const letzte = (st.pruefungen || [])[0];
  const ohne = letzte && letzte.zeitpunkt === st.zuletzt_geprueft ? " – keine Änderung" : "";
  const geprueft = st.zuletzt_geprueft ? `Zuletzt geprüft ${zeitText(st.zuletzt_geprueft)}${ohne}` : "Noch nicht geprüft";
  // Uhr des Servers (im Mock-Modus simuliert), nicht die des Browsers
  const alt = st.zuletzt_geprueft && datum(st.jetzt) - datum(st.zuletzt_geprueft) > 2 * 3600000;
  const pl = st.prueflauf;
  const kaputt = pl && pl.fehler.length;
  const prueflauf = pl ? h("p", { class: kaputt ? "fehler" : "klein", tid: "sicherung-prueflauf", role: kaputt ? "alert" : null },
    kaputt ? `Prüflauf ${zeitText(pl.zeitpunkt)}: ${pl.fehler.length === 1 ? "1 Punkt lässt" : `${pl.fehler.length} Punkte lassen`} `
      + "sich nicht herstellen. Der nächste Punkt wird vollständig gesichert."
      : `Prüflauf ${zeitText(pl.zeitpunkt)}: alle Punkte herstellbar.`) : null;
  return h("section", { class: "karte sp-kachel", tid: "sicherung-stand", "data-zustand": alt || kaputt ? "fehler" : zustand },
    h("h3", null, "Aktueller Stand"), h("p", null, text),
    h("p", { class: "klein" }, alt ? `${geprueft} – die stündliche Sicherung läuft nicht.` : geprueft), prueflauf);
}

function speicherKachel(st) {
  const g = st.gesamt;
  const balken = h("div", { class: "sp-balken", role: "img", "aria-label": "Größe je Stufe" },
    STUFEN.filter(([k]) => g.stufen[k]).map(([k, text]) => h("span", { class: `sp-stufe sp-stufe-${k}`,
      style: `flex-grow:${g.stufen[k]}`, title: `${text}: ${groesseText(g.stufen[k])}` })));
  const legende = h("ul", { class: "sp-legende" }, STUFEN.filter(([k]) => g.stufen[k]).map(([k, text]) =>
    h("li", null, h("span", { class: `sp-punkt sp-stufe-${k}`, "aria-hidden": "true" }), `${text} ${groesseText(g.stufen[k])}`)));
  return h("section", { class: "karte sp-kachel", tid: "sicherung-speicher" }, h("h3", null, "Speicher"),
    h("p", null, h("strong", { tid: "sicherung-gesamt", "data-bytes": String(g.groesse) }, groesseText(g.groesse)),
      ` in ${g.anzahl === 1 ? "1 Punkt" : `${g.anzahl} Punkten`}${st.frei !== null ? ` · ${groesseText(st.frei)} frei` : ""}`),
    balken, legende,
    h("p", { class: "klein" }, "Alle Sicherungen liegen auf diesem Server. Fällt sein Datenträger aus, sind sie mit "
      + "betroffen – laden Sie gelegentlich einen Punkt herunter."));
}

function einspielenDialog(ausloeser, neuLaden) {
  return dialog("einspielen-dialog", "Sicherung einspielen", (inhalt, d) => {
    const datei = h("input", { type: "file", tid: "sp-datei", accept: ".zip,application/zip" });
    const ausgabe = h("div", { "aria-live": "polite" });
    const senden = (params) => {
      const fd = new FormData();
      fd.append("datei", datei.files[0], datei.files[0].name);
      return api("POST", `/api/sicherung/einspielen?${new URLSearchParams(params)}`, undefined, { formular: fd });
    };
    const ok = knopf("Einspielen", { tid: "sp-einspielen", class: "knopf knopf-gefahr", disabled: true, onclick: async (e) => {
      if (!(await bestaetigen("Der aktuelle Stand wird vorher gesichert, danach werden alle Daten durch die Sicherung ersetzt. "
        + "Zugangsdaten und Anmeldung bleiben.", { ja: "Bestand ersetzen", ausloeser: e.currentTarget }))) return;
      await imDialog(d, ok, () => aktion(() => senden({ bestaetigt: "true" }),
        { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Sicherung eingespielt." }));
      await neuLaden();
    } });
    datei.addEventListener("change", async () => {
      ok.disabled = true;
      if (!datei.files.length) return;
      try {
        const r = await senden({ trocken: "true" });
        ausgabe.replaceChildren(h("p", null, r.geaendert ? `Einspielen: ${wirkungText(r.unterschied)}`
          : "Die Sicherung entspricht dem aktuellen Bestand.", ` (erstellt ${zeitText(r.manifest.erstellt)})`));
        ok.disabled = !r.geaendert;
      } catch (f) { ausgabe.replaceChildren(h("p", { class: "fehler", role: "alert" }, f.message)); }
    });
    inhalt.append(feld("Sicherungsdatei", datei), ausgabe, knopfLeiste(ok, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser });
}

export async function sicherungSeite(seite) {
  seite.classList.add("seite-sicherung");
  const kacheln = h("div", { class: "sp-kacheln" });
  const liste = h("div", { class: "pr-liste sp-liste", tid: "sicherung-liste" });
  const leerEl = h("p", { class: "leer pr-leer", hidden: true }, "Noch keine Sicherungspunkte. Der erste entsteht zur nächsten vollen Stunde.");
  const anlegen = knopf("Sicherungspunkt jetzt anlegen", { tid: "sicherung-anlegen", class: "knopf knopf-haupt" });
  const einspielen = knopf("Sicherung einspielen …", { tid: "sicherung-datei-einspielen" });
  seite.append(h("div", { class: "seiten-kopf pr-kopf" }, h("div", null, h("h1", null, "Sicherungspunkte"),
    h("p", { class: "pr-stand" }, "Stündlich, nur bei Änderungen; ältere Punkte je Tag, Woche und Monat.")),
  knopfLeiste(anlegen, einspielen)), kacheln, liste, leerEl);

  async function neuLaden() {
    const st = await api("GET", "/api/sicherung/punkte");
    kacheln.replaceChildren(standKachel(st), speicherKachel(st));
    const oeffnen = (p, el) => { try { punktFenster(p, el, neuLaden); } catch (e) { melde("fehler", e.message); } };
    liste.replaceChildren(...zeitleiste(st.punkte, st.pruefungen || [], oeffnen, datum(st.jetzt)));   // Uhr des Servers
    leerEl.hidden = st.punkte.length > 0 || (st.pruefungen || []).length > 0;
  }

  anlegen.addEventListener("click", () => dialog("punkt-anlegen-dialog", "Sicherungspunkt anlegen", (inhalt, d) => {
    const name = h("input", { type: "text", maxlength: "100", tid: "punkt-anlegen-name", placeholder: "zum Beispiel „Vor dem Aufräumen“" });
    const ok = knopf("Anlegen", { class: "knopf knopf-haupt", tid: "punkt-anlegen-ok" });
    ok.addEventListener("click", () => imDialog(d, ok, async () => {
      const r = await api("POST", "/api/sicherung/punkte", { name: name.value.trim() || null });
      d.schliessen(true);
      melde("erfolg", r.neu ? "Sicherungspunkt angelegt." : `Dieser Stand ist bereits gesichert (${punktText(r)}).`);
      await neuLaden();
    }));
    inhalt.append(feld("Name (freiwillig)", name), knopfLeiste(ok, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
  }, { ausloeser: anlegen }));
  einspielen.addEventListener("click", () => einspielenDialog(einspielen, neuLaden));

  // Pfeiltasten springen zwischen den Punkten (wie in den übrigen Listen)
  liste.addEventListener("keydown", (e) => {
    if (!["ArrowDown", "ArrowUp"].includes(e.key) || e.altKey || e.ctrlKey || e.metaKey) return;
    const titel = [...liste.querySelectorAll(".sp-zeile .pr-titel")].filter((x) => x.offsetParent !== null);
    const i = titel.indexOf(document.activeElement);
    if (i < 0) return;
    const j = e.key === "ArrowDown" ? Math.min(i + 1, titel.length - 1) : Math.max(i - 1, 0);
    titel[j].focus();
    e.preventDefault();
  });
  await neuLaden();
  return { titel: "Sicherungspunkte", aktualisieren: () => neuLaden().catch(() => {}) };
}
