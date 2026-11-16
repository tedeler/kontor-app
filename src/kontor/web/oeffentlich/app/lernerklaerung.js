/* Kontor – „Warum?“ des Lernmodells je Buchung (D-183). Lesezugriff über GET /api/buchungen/{id}/lernmodell.
 * Die Beiträge sind exakt: Faktor je Merkmal der besten gegenüber der zweitbesten Kategorie (lernmodell.md 4). */
import { api, betragEl, datumText, h, pfadVon } from "./kern.js";

/** Wie norm() im Server: Kleinbuchstaben, ä→ae, ö→oe, ü→ue, ß→ss. */
const norm = (s) => String(s || "").toLowerCase().replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss");

const prozent = (p) => `${Math.floor((p + 5) / 10)} %`;

function faktorText(fp) {
  if (fp >= 1000) {
    const f = fp / 1000;
    return `×${f >= 10 ? Math.round(f) : f.toFixed(1).replace(".", ",")}`;
  }
  const f = 1000 / Math.max(fp, 1);
  return `÷${f >= 10 ? Math.round(f) : f.toFixed(1).replace(".", ",")}`;
}

function merkmalName(m) {
  if (m.art === "empfaenger") return `Empfänger „${m.text}“`;
  if (m.art === "wort") return `Wort „${m.text}“`;
  return m.text;
}

/** Balken: rechts (grün) spricht dafür, links (rot) dagegen; Länge ~ log des Faktors. */
function balken(fp) {
  const st = Math.min(Math.abs(Math.log10(Math.max(fp, 1) / 1000)) / 3, 1);
  const breite = `${Math.round(st * 50)}%`;
  const dafuer = fp >= 1000;
  return h("span", { class: "lern-balken", "aria-hidden": "true" },
    h("span", { class: dafuer ? "lern-balken-dafuer" : "lern-balken-dagegen",
      style: dafuer ? `left:50%;width:${breite}` : `right:50%;width:${breite}` }));
}

/** Verwendungszweck mit markierten Wörtern (Wörter wie lernmodell.md 2). */
function zweckMarkiert(zweck, merkmale) {
  const wert = new Map(merkmale.filter((m) => m.art === "wort").map((m) => [m.text, m]));
  const teile = String(zweck || "").split(/([^A-Za-z0-9ÄÖÜäöüß]+)/);
  return h("p", { class: "lern-zweck", tid: "lern-zweck" }, teile.map((t) => {
    const m = wert.get(norm(t));
    if (!m || !t) return document.createTextNode(t);   // auch reine Leerzeichen (h() ließe sie weg)
    const art = !m.bekannt ? "unbekannt" : m.faktor_promille == null ? "neutral"
      : m.faktor_promille >= 1000 ? "dafuer" : "dagegen";
    return h("mark", { class: `lern-wort lern-wort-${art}`, title: m.bekannt ? `${m.anzahl} frühere Buchungen` : "unbekannt" }, t);
  }));
}

function satz(e) {
  if (e.grund === "kein_modell") return "Es gibt noch keine kategorisierten Buchungen, aus denen das Lernmodell lernen könnte.";
  if (e.grund === "unbekannt") {
    return "Weder der Empfänger noch ein Wort des Verwendungszwecks kommt in kategorisierten Buchungen vor. "
      + "Der Betrag allein reicht für eine Einschätzung nicht.";
  }
  const kat = pfadVon(e.beste_kategorie_id);
  const bekannt = e.merkmale.filter((m) => m.bekannt && m.art !== "betrag");
  const staerkstes = bekannt.slice().sort((a, b) => (b.faktor_promille || 0) - (a.faktor_promille || 0)
    || b.anzahl_kategorie - a.anzahl_kategorie)[0];
  const beleg = staerkstes ? ` ${merkmalName(staerkstes)}: ${staerkstes.anzahl_kategorie} von ${staerkstes.anzahl} `
    + `früheren Buchungen waren ${kat}.` : "";
  const p = (e.kandidaten[0] || {}).sicherheit || 0;
  if (e.grund === "vorschlag") return `${kat} mit ${prozent(p)}.${beleg}`;
  return `Am wahrscheinlichsten ist ${kat} mit ${prozent(p)}, vorgeschlagen wird erst ab ${prozent(e.schwelle_promille)}.${beleg}`;
}

function inhalt(e, b) {
  const teile = [h("p", { tid: "lern-satz" }, satz(e))];
  const vergleich = e.vergleich_kategorie_id;
  if (e.beste_kategorie_id != null && vergleich != null) {
    const zeilen = e.merkmale.map((m) => h("li", { class: "lern-merkmal", tid: "lern-merkmal", "data-merkmal": m.merkmal,
      "data-faktor": m.faktor_promille == null ? "" : String(m.faktor_promille) },
    h("span", { class: "lern-merkmal-name" }, merkmalName(m)),
    m.bekannt && m.faktor_promille != null ? balken(m.faktor_promille) : h("span", { class: "lern-balken" }),
    h("span", { class: "lern-merkmal-wert" }, !m.bekannt ? "unbekannt, zählt nicht"
      : `${faktorText(m.faktor_promille)} · ${m.anzahl_kategorie} von ${m.anzahl} in ${pfadVon(e.beste_kategorie_id)}, `
        + `${m.anzahl_vergleich} in ${pfadVon(vergleich)}`)));
    const g = e.grundwert;
    zeilen.push(h("li", { class: "lern-merkmal", tid: "lern-merkmal", "data-merkmal": "grundwert",
      "data-faktor": String(g.faktor_promille) },
    h("span", { class: "lern-merkmal-name" }, "Häufigkeit der Kategorie"), balken(g.faktor_promille),
    h("span", { class: "lern-merkmal-wert" }, `${faktorText(g.faktor_promille)} · ${g.anzahl_kategorie} gegenüber `
      + `${g.anzahl_vergleich} Buchungen`)));
    teile.push(h("p", { class: "klein" }, `Was für ${pfadVon(e.beste_kategorie_id)} und gegen ${pfadVon(vergleich)} `
      + "(die nächstbeste Kategorie) spricht. Die Faktoren multiplizieren sich."),
    h("ul", { class: "lern-merkmale", tid: "lern-merkmale" }, zeilen));
  }
  teile.push(zweckMarkiert(b.verwendungszweck, e.merkmale));
  if (e.aehnliche.length) {
    teile.push(h("p", { class: "klein" }, "Ähnliche frühere Buchungen (gleicher Empfänger oder gleiche Wörter):"),
      h("ul", { class: "lern-aehnliche", tid: "lern-aehnliche" }, e.aehnliche.map((a) => h("li", null,
        h("a", { href: `/buchungen/${a.buchung_id}`, tid: `lern-aehnlich-${a.buchung_id}` }, datumText(a.datum)),
        document.createTextNode(` ${a.empfaenger || "–"} `), betragEl("span", a.betrag),
        document.createTextNode(" → "), h("strong", null, pfadVon(a.kategorie_id))))));
  }
  teile.push(h("p", { class: "klein" }, h("a", { href: "/lernmodell" }, "Wie gut ist das Lernmodell insgesamt?")));
  return teile;
}

/** Aufklappbarer Abschnitt „Warum?“; lädt die Erklärung erst beim Öffnen. */
export function warumAbschnitt(b, titel) {
  const koerper = h("div", { class: "lern-erklaerung", tid: "lern-erklaerung" }, h("p", { class: "klein" }, "Wird geladen …"));
  const el = h("details", { class: "lern-warum", tid: "lern-warum" }, h("summary", null, titel || "Warum?"), koerper);
  let geladen = false;
  el.addEventListener("toggle", () => {
    if (!el.open || geladen) return;
    geladen = true;
    api("GET", `/api/buchungen/${b.id}/lernmodell`).then((e) => {
      koerper.replaceChildren(...inhalt(e, b));
      koerper.dataset.grund = e.grund;
    }).catch(() => { koerper.replaceChildren(h("p", { class: "klein" }, "Die Erklärung ist gerade nicht verfügbar.")); geladen = false; });
  });
  return el;
}
