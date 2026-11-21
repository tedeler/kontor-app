// Einzelheiten einer Änderung des Protokolls (D-237): ein Fenster, das je betroffenem Objekt zeigt, welche Angaben
// sich geändert haben (vorher → nachher). Nur lesend; alle Texte aus dem Buchbestand laufen über h()/textContent.
import { api, betragText, datumText, h, kontoNach, kontoPfad, stamm, zeitText } from "./kern.js";
import { dialog, knopf, knopfLeiste } from "./ui.js";

const OBJEKT_NAMEN = { konto: ["Konto", "Konten"], empfaenger: ["Empfänger", "Empfänger"], tag: ["Tag", "Tags"],
  buchung: ["Buchung", "Buchungen"], regel: ["Regel", "Regeln"], verdacht: ["Dublettenverdacht", "Dublettenverdachte"],
  abstimmung: ["Abstimmung", "Abstimmungen"], vorlage: ["Split-Vorlage", "Split-Vorlagen"], kredit: ["Kredit", "Kredite"],
  postfach: ["Postfach", "Postfächer"], dokument: ["Dokument", "Dokumente"], erwartung: ["Erwartete Zahlung", "Erwartete Zahlungen"] };
const ART_TEXT = { angelegt: "angelegt", geaendert: "geändert", geloescht: "gelöscht" };
const QUELLEN = { manuell: "von Hand", import: "Import", sync: "Synchronisation", regeln: "Regel", umbuchung: "Umbuchungserkennung",
  rueckgaengig: "Rückgängig", lernmodell: "Lernmodell", vorlage: "Split-Vorlage", sicherung: "Sicherung", kredit: "Kredit", mail: "Mail-Abgleich" };
const FELD_NAMEN = { datum: "Datum", empfaenger_id: "Empfänger", verwendungszweck: "Verwendungszweck", status: "Status", splits: "Aufteilung",
  tag_ids: "Tags", extern_ids: "Kennungen der Herkunft", extern_id: "Kennung der Herkunft", vorschlag: "Vorschlag", gegen_iban: "Gegen-IBAN",
  name: "Name", aliase: "Aliase", standardkategorie_id: "Standardkategorie", eltern_id: "Übergeordnetes Konto", art: "Art",
  konto_id: "Konto", kategorie_id: "Kategorie", betrag: "Betrag", memo: "Notiz", abstimmung_id: "Abstimmung", dokument_ids: "Dokumente",
  buchung_ids: "Buchungen", iban: "IBAN", waehrung: "Währung", bedingungen: "Bedingungen", aktionen: "Aktionen", aktiv: "Aktiv",
  position: "Reihenfolge", automatisch: "Automatisch anwenden", wiederkehrend: "Wiederkehrend", stichtag: "Stichtag", saldo: "Saldo",
  adresse: "Adresse", dateiname: "Dateiname", typ: "Typ", groesse: "Größe", zustand: "Zustand", anbieter: "Anbieter", grund: "Grund",
  kandidaten: "Mögliche Gegenstücke", erstellt_am: "Erstellt am", faellig: "Fällig", frist: "Frist", herkunft: "Herkunft", versteckt: "Versteckt" };
const GRENZE = 50;           // so viele Objekte zeigt das Fenster zunächst; weitere auf Knopfdruck
const gleich = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const istLeer = (w) => w === null || w === undefined || w === "" || (Array.isArray(w) && !w.length);

function feldName(schluessel) {
  return FELD_NAMEN[schluessel] || schluessel.replace(/_ids?$/, "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
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
  if (typeof w === "number" && /betrag|saldo|summe|rate|zins_cent/.test(schluessel)) return betragText(w);
  if (typeof w === "string" && /^\d{4}-\d{2}-\d{2}$/.test(w)) return datumText(w);
  if (typeof w === "string" && /^\d{4}-\d{2}-\d{2}T/.test(w)) return zeitText(w);
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
    h("h3", null, h("span", { class: `ae-art ae-${e.art}` }, ART_TEXT[e.art] || e.art), " ", namen[0], ": ",
      h("span", { class: "ae-titel" }, objektTitel(e, n)), " ", h("small", { class: "klein" }, `#${e.objekt_id}`)),
    zeilen.length ? h("table", { class: "tabelle ae-tabelle" },
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

/** Öffnet das Fenster mit den Einzelheiten der Änderung `id`. */
export async function aenderungFenster(id, ausloeser) {
  const a = await api("GET", `/api/aenderungen/${id}`);
  const n = nachschlag(a);
  return dialog("aenderung-dialog", `Änderung #${a.id}: ${a.beschreibung}`, (inhalt, d) => {
    const wirksam = a.rueckgaengig_durch === null;
    const kopf = h("dl", { class: "ae-kopf" },
      h("dt", null, "Zeitpunkt"), h("dd", null, zeitText(a.zeitpunkt)),
      h("dt", null, "Quelle"), h("dd", null, QUELLEN[a.quelle] || a.quelle),
      h("dt", null, "Vorgang"), h("dd", { tid: "ae-aktion" }, a.aktion),
      h("dt", null, "Umfang"), h("dd", { tid: "ae-umfang" }, zusammenfassung(a.eintraege)),
      h("dt", null, "Stand"), h("dd", { tid: "ae-stand" }, wirksam ? "wirksam" : `rückgängig gemacht durch Änderung #${a.rueckgaengig_durch}`),
      ...(a.rueckgaengig_von.length ? [h("dt", null, "Macht rückgängig"), h("dd", null, a.rueckgaengig_von.map((x) => `#${x}`).join(", "))] : []));
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
