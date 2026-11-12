/* Kontor – Dokumente an Buchungen (Feature „dokumente“, D-123).
 *
 * Anhängen per Dateiauswahl, Kamera (mobil), Ziehen auf eine Buchung und aus einem Postfach; Betrachter für PDF,
 * Bilder und E-Mails. Jede Änderung läuft über aktion() (Rückgängig, Neuladen). HTML von E-Mails wird nur im
 * abgeschotteten Rahmen des Servers gezeigt (sandbox, eigene Inhaltsrichtlinie, keine externen Inhalte). */
import { BESTAND, aktion, api, betragEl, datumText, h, kontoNach, melde, oberflaeche, zeitText } from "./kern.js";
import { dialog, knopf, knopfLeiste } from "./ui.js";

export const ANNAHME = "application/pdf,.pdf,message/rfc822,.eml,image/jpeg,image/png,image/webp";
const KAMERA_MAX_KANTE = 2400;          // Fotos der Kamera werden auf diese Kantenlänge verkleinert
const KAMERA_QUALITAET = 0.85;

export function groesseText(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(Math.round(n / 104857.6) / 10).toLocaleString("de-DE")} MB`;
}

export function symbol(typ) {
  if (typ === "application/pdf") return "📄";
  if (typ === "message/rfc822") return "✉️";
  if (typ && typ.startsWith("image/")) return "🖼️";
  return "📎";
}

// ---------------------------------------------------------------- Hochladen

/** Foto der Kamera verkleinern (JPEG); ohne Erfolg die Originaldatei. */
async function kameraVerkleinern(datei) {
  try {
    const bild = await createImageBitmap(datei, { imageOrientation: "from-image" });
    const f = Math.min(1, KAMERA_MAX_KANTE / Math.max(bild.width, bild.height));
    if (f === 1 && datei.size < 2 * 1024 * 1024 && datei.type === "image/jpeg") return datei;
    const c = document.createElement("canvas");
    c.width = Math.round(bild.width * f);
    c.height = Math.round(bild.height * f);
    c.getContext("2d").drawImage(bild, 0, 0, c.width, c.height);
    const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", KAMERA_QUALITAET));
    if (!blob) return datei;
    const stamm = (datei.name || "Foto").replace(/\.[^.]*$/, "") || "Foto";
    return new File([blob], `${stamm}.jpg`, { type: "image/jpeg" });
  } catch (e) {
    return datei;
  }
}

/** Dateien an Buchungen hängen: je Datei eine Änderung (einzeln rückgängig zu machen). */
export async function hochladen(buchungIds, dateien, quelle) {
  const liste = [...dateien];
  if (!liste.length || !buchungIds.length) return;
  for (let i = 0; i < liste.length; i++) {
    let datei = liste[i];
    if (quelle === "kamera") datei = await kameraVerkleinern(datei);
    const fd = new FormData();
    fd.append("datei", datei, datei.name || (quelle === "kamera" ? "Foto.jpg" : "Dokument"));
    const ziel = `/api/dokumente?${buchungIds.map((b) => `buchung_id=${b}`).join("&")}&quelle=${quelle || "upload"}`;
    const letzte = i === liste.length - 1;
    try {
      await aktion(() => api("POST", ziel, undefined, { formular: fd }), {
        erfolg: (d) => `„${d.dateiname}“ angehängt${buchungIds.length > 1 ? ` (${buchungIds.length} Buchungen)` : ""}.`,
        ohneNeuLaden: !letzte,
      });
    } catch (e) { /* Meldung kam von aktion(); nächste Datei trotzdem */ }
  }
}

/** Unsichtbare Dateiauswahl öffnen. kamera: Rückkamera direkt (mobil). */
export function dateiWaehlen(buchungIds, optionen) {
  const o = optionen || {};
  const eingabe = h("input", { type: "file", accept: o.kamera ? "image/*" : ANNAHME, hidden: true,
    tid: o.kamera ? "dokument-kamera-eingabe" : "dokument-datei-eingabe" });
  if (o.kamera) eingabe.setAttribute("capture", "environment");
  else eingabe.multiple = true;
  eingabe.addEventListener("change", () => {
    const dateien = [...eingabe.files];
    eingabe.remove();
    hochladen(buchungIds, dateien, o.kamera ? "kamera" : "upload");
  });
  eingabe.addEventListener("cancel", () => eingabe.remove());
  document.body.append(eingabe);
  eingabe.click();
}

// ---------------------------------------------------------------- E-Mail aus Postfach

export function mailDialog(buchungIds, ausloeser) {
  dialog("mail-auswahl-dialog", "E-Mail anhängen", async (inhalt, d) => {
    const suche = h("input", { type: "search", tid: "mail-auswahl-suche", placeholder: "Absender oder Betreff",
      "aria-label": "E-Mails durchsuchen" });
    const liste = h("ul", { class: "mail-auswahl", tid: "mail-auswahl-liste", role: "listbox", "aria-label": "E-Mails" },
      h("li", { class: "leer" }, "Lade E-Mails …"));
    inhalt.append(suche, liste, knopfLeiste(knopf("Abbrechen", { tid: "mail-auswahl-abbrechen", onclick: () => d.schliessen(null) })));
    let mails = [];
    try {
      const erste = await api("GET", "/api/mail/nachrichten?pro_seite=500");
      mails = erste.eintraege;
      const seiten = Math.ceil(erste.gesamt / 500);
      if (seiten > 1) {   // neueste stehen hinten: letzte Seite zusätzlich laden
        const letzte = await api("GET", `/api/mail/nachrichten?pro_seite=500&seite=${seiten}`);
        mails = mails.concat(letzte.eintraege);
      }
    } catch (e) {
      liste.replaceChildren(h("li", { class: "leer" }, e.message || "Die E-Mails konnten nicht geladen werden."));
      return;
    }
    const gesehen = new Set();
    mails = mails.filter((m) => !gesehen.has(m.id) && gesehen.add(m.id)).reverse();   // neueste zuerst
    const zeichnen = () => {
      const q = suche.value.trim().toLocaleLowerCase("de-DE");
      const treffer = mails.filter((m) => !q || `${m.absender} ${m.betreff}`.toLocaleLowerCase("de-DE").includes(q)).slice(0, 200);
      if (!mails.length) {
        liste.replaceChildren(h("li", { class: "leer" }, "Keine abgerufenen E-Mails. Postfächer richtest du unter Einstellungen ein."));
        return;
      }
      liste.replaceChildren(...(treffer.length ? treffer.map((m) => {
        const el = h("li", { role: "option", tabindex: "0", tid: `mail-auswahl-${m.id}`, class: "mail-eintrag" },
          h("div", { class: "mail-betreff" }, m.betreff || "(ohne Betreff)"),
          h("div", { class: "klein" }, m.absender, " · ", zeitText(m.empfangen)));
        const waehlen = async () => {
          d.sperren(true);
          try {
            await aktion(() => api("POST", "/api/dokumente/aus-mail", { nachricht_id: m.id, buchung_ids: buchungIds }), {
              erfolg: "E-Mail angehängt.", danach: () => d.schliessen(true) });
          } catch (e) {
            d.sperren(false);
            if (d.offen) d.fehler(e.message || String(e));
          }
        };
        el.addEventListener("click", waehlen);
        el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); waehlen(); } });
        return el;
      }) : [h("li", { class: "leer" }, "Keine passende E-Mail.")]));
    };
    suche.addEventListener("input", zeichnen);
    zeichnen();
  }, { schliessenKnopf: "mail-auswahl-schliessen", klasse: "dialog-breit", ausloeser });
}

// ---------------------------------------------------------------- Betrachter

const inhaltUrl = (id, laden) => `/api/dokumente/${id}/inhalt${laden ? "?herunterladen=true" : ""}`;

function pdfAnsicht(url, name) {
  // Mobile Browser zeigen PDFs in Rahmen oft nicht an: dort zusätzlich deutlich „Öffnen“
  const rahmen = h("iframe", { class: "betrachter-pdf", tid: "betrachter-pdf", src: url, title: name });
  const mobil = oberflaeche.istMobil();
  return h("div", { class: "betrachter-flaeche" }, mobil
    ? h("p", { class: "betrachter-hinweis" }, h("a", { href: url, target: "_blank", rel: "noopener", class: "knopf knopf-haupt",
      tid: "betrachter-oeffnen" }, "PDF öffnen"))
    : null, rahmen);
}

function bildAnsicht(url, name) {
  const img = h("img", { class: "betrachter-bild", tid: "betrachter-bild", src: url, alt: name });
  img.addEventListener("click", () => img.classList.toggle("gross"));
  return h("div", { class: "betrachter-flaeche betrachter-flaeche-bild" }, img);
}

function adressText(liste) {
  return liste.map((a) => (a.name ? `${a.name} <${a.adresse}>` : a.adresse)).join(", ");
}

async function mailAnsicht(dok, betrachten) {
  const flaeche = h("div", { class: "betrachter-flaeche betrachter-mail", tid: "betrachter-mail" }, h("p", { class: "leer" }, "Lade E-Mail …"));
  try {
    const m = await api("GET", `/api/dokumente/${dok.id}/mail`);
    const kopf = h("dl", { class: "mail-kopf", tid: "mail-kopf" },
      h("dt", null, "Von"), h("dd", { tid: "mail-von" }, adressText(m.von)),
      m.an.length ? [h("dt", null, "An"), h("dd", null, adressText(m.an))] : null,
      m.cc.length ? [h("dt", null, "Cc"), h("dd", null, adressText(m.cc))] : null,
      m.datum ? [h("dt", null, "Datum"), h("dd", null, zeitText(m.datum))] : null,
      h("dt", null, "Betreff"), h("dd", { tid: "mail-betreff" }, m.betreff || "(ohne Betreff)"));
    const text = h("pre", { class: "mail-text", tid: "mail-text" }, m.text);
    const koerper = h("div", { class: "mail-koerper" });
    let ansicht = m.html ? "html" : "text";
    const umschalter = m.html ? knopf("", { class: "knopf knopf-klein", tid: "mail-ansicht-umschalten" }) : null;
    const zeigen = () => {
      if (ansicht === "html") {
        koerper.replaceChildren(h("iframe", { class: "mail-html", tid: "mail-html", src: `/api/dokumente/${dok.id}/mail/html`,
          sandbox: "allow-popups allow-popups-to-escape-sandbox", referrerpolicy: "no-referrer", title: "Inhalt der E-Mail" }));
      } else koerper.replaceChildren(text);
      if (umschalter) umschalter.textContent = ansicht === "html" ? "Als Text zeigen" : "Formatiert zeigen";
    };
    if (umschalter) umschalter.addEventListener("click", () => { ansicht = ansicht === "html" ? "text" : "html"; zeigen(); });
    zeigen();
    const anhaenge = m.anhaenge.filter((a) => !a.inline);
    const anh = anhaenge.length ? h("ul", { class: "mail-anhaenge", tid: "mail-anhaenge" }, anhaenge.map((a) => {
      const url = `/api/dokumente/${dok.id}/mail/anhaenge/${a.nr}`;
      const ansehbar = a.mime_typ === "application/pdf" || /^image\/(jpeg|png|webp|gif)$/.test(a.mime_typ);
      return h("li", { tid: `mail-anhang-${a.nr}` }, symbol(a.mime_typ), " ",
        ansehbar ? h("button", { type: "button", class: "knopf-link", tid: `mail-anhang-ansehen-${a.nr}`,
          onclick: () => betrachten({ id: dok.id, dateiname: a.dateiname, mime_typ: a.mime_typ, groesse: a.groesse, url }) },
        a.dateiname) : h("span", null, a.dateiname),
        h("small", null, " ", groesseText(a.groesse), " "),
        h("a", { href: `${url}?herunterladen=true`, class: "knopf-link klein", tid: `mail-anhang-laden-${a.nr}`, download: a.dateiname },
          "Herunterladen"));
    })) : null;
    flaeche.replaceChildren(kopf, umschalter ? h("div", { class: "mail-umschalter" }, umschalter) : null, koerper,
      anh ? h("h3", { class: "klein" }, "Anhänge") : null, anh);
  } catch (e) {
    flaeche.replaceChildren(h("p", { class: "fehler" }, e.message || "Die E-Mail konnte nicht gelesen werden."));
  }
  return flaeche;
}

// ---------------------------------------------------------------- Verknüpfte Buchungen

function buchungKurz(b) {
  return [datumText(b.datum), " · ", b.empfaenger ? b.empfaenger.name : (b.verwendungszweck || "ohne Empfänger"), " · "];
}

/** Konto für den Sprung zur Buchung: erstes Bestandskonto ihrer Splits, sonst das erste Konto. */
function sprungKonto(b) {
  const best = b.splits.find((s) => { const k = kontoNach(s.konto_id); return k && BESTAND.has(k.art); });
  return (best || b.splits[0]).konto_id;
}

/** Abschnitt „Hängt an“ im Betrachter: Buchungen des Dokuments, Lösen, weitere verknüpfen. */
async function buchungenAbschnitt(dok, d) {
  const el = h("div", { class: "betrachter-buchungen", tid: "betrachter-buchungen" }, h("span", { class: "klein" }, "Lade …"));
  const laden = async () => {
    try {
      const info = await api("GET", `/api/dokumente/${dok.id}`);
      const buchungen = await Promise.all(info.buchung_ids.map((id) => api("GET", `/api/buchungen/${id}`)));
      el.dataset.anzahl = String(buchungen.length);
      el.replaceChildren(h("h3", { class: "klein" }, buchungen.length === 1 ? "Hängt an 1 Buchung" : `Hängt an ${buchungen.length} Buchungen`),
        h("ul", { class: "betrachter-buchungen-liste" }, buchungen.map((b) => h("li", { tid: `betrachter-buchung-${b.id}` },
          h("button", { type: "button", class: "knopf-link", tid: `betrachter-zur-buchung-${b.id}`, title: "Zur Buchung",
            onclick: () => { d.schliessen(null); oberflaeche.zurBuchung(sprungKonto(b), b.id); } }, ...buchungKurz(b), betragEl("span", b.betrag)),
          h("button", { type: "button", class: "mini-knopf", tid: `betrachter-loesen-${b.id}`, title: "Von dieser Buchung lösen",
            "aria-label": `Dokument von der Buchung vom ${datumText(b.datum)} lösen`, onclick: async () => {
              await loesen(dok, b.id);
              if (buchungen.length > 1) laden(); else d.schliessen(null);
            } }, "×")))),
        knopf("Mit weiteren Buchungen verknüpfen…", { class: "knopf knopf-klein", tid: "betrachter-verknuepfen",
          onclick: (e) => verknuepfenDialog(dok, info.buchung_ids, e.currentTarget).then((ok) => { if (ok) laden(); }) }));
    } catch (e) {
      el.replaceChildren(h("p", { class: "fehler" }, e.message || String(e)));
    }
  };
  await laden();
  return el;
}

/** Buchungen suchen und markieren; Ergebnis true, wenn verknüpft wurde. */
export function verknuepfenDialog(dok, schonIds, ausloeser) {
  const schon = new Set(schonIds);
  const gewaehlt = new Set();
  const d = dialog("verknuepfen-dialog", `„${dok.dateiname}“ verknüpfen`, (inhalt, dd) => {
    const suche = h("input", { type: "search", tid: "verknuepfen-suche", placeholder: "Empfänger, Verwendungszweck, Betrag …",
      "aria-label": "Buchungen suchen" });
    const liste = h("ul", { class: "verknuepfen-liste", tid: "verknuepfen-liste" });
    const ok = knopf("Verknüpfen", { class: "knopf knopf-haupt", tid: "verknuepfen-ok", disabled: true });
    let nr = 0;
    const suchen = async () => {
      const meine = ++nr;
      const q = suche.value.trim();
      try {
        const r = await api("GET", `/api/buchungen?pro_seite=50&sortierung=-datum${q ? `&suche=${encodeURIComponent(q)}` : ""}`);
        if (meine !== nr) return;
        liste.replaceChildren(...(r.eintraege.length ? r.eintraege.map((b) => {
          const box = h("input", { type: "checkbox", tid: `verknuepfen-buchung-${b.id}`, checked: schon.has(b.id) || gewaehlt.has(b.id),
            disabled: schon.has(b.id) });
          box.addEventListener("change", () => {
            if (box.checked) gewaehlt.add(b.id); else gewaehlt.delete(b.id);
            ok.disabled = !gewaehlt.size;
            ok.textContent = gewaehlt.size > 1 ? `Mit ${gewaehlt.size} Buchungen verknüpfen` : "Verknüpfen";
          });
          return h("li", null, h("label", { class: "verknuepfen-eintrag" }, box, " ", ...buchungKurz(b), betragEl("span", b.betrag),
            schon.has(b.id) ? h("small", null, " (schon verknüpft)") : null));
        }) : [h("li", { class: "leer" }, "Keine Buchung gefunden.")]));
      } catch (e) { dd.fehler(e.message || String(e)); }
    };
    let warten;
    suche.addEventListener("input", () => { clearTimeout(warten); warten = setTimeout(suchen, 250); });
    ok.addEventListener("click", async () => {
      dd.sperren(true);
      try {
        await aktion(() => api("POST", `/api/dokumente/${dok.id}/buchungen`, { buchung_ids: [...gewaehlt] }), {
          erfolg: `„${dok.dateiname}“ verknüpft.`, danach: () => dd.schliessen(true) });
      } catch (e) {
        dd.sperren(false);
        if (dd.offen) dd.fehler(e.message || String(e));
      }
    });
    inhalt.append(suche, liste, knopfLeiste(ok, knopf("Abbrechen", { tid: "verknuepfen-abbrechen", onclick: () => dd.schliessen(null) })));
    suchen();
  }, { schliessenKnopf: "verknuepfen-schliessen", klasse: "dialog-breit", ausloeser });
  return d.ergebnis.then((w) => w === true);
}

/** Betrachter für die Dokumente einer Buchung (Liste), beginnend bei index. */
export function betrachter(dokumente, index, ausloeser) {
  let i = index || 0;
  let stapel = [];        // geöffnete Anhänge einer Mail (zurück zur Mail)
  return dialog("dokument-betrachter", "Dokument", (inhalt, d) => {
    const titel = d.el.querySelector(".dialog-kopf h2");
    const flaeche = h("div", { class: "betrachter-inhalt" });
    const zurueck = knopf("‹", { class: "knopf knopf-klein", tid: "betrachter-voriges", "aria-label": "Voriges Dokument" });
    const vor = knopf("›", { class: "knopf knopf-klein", tid: "betrachter-naechstes", "aria-label": "Nächstes Dokument" });
    const zaehler = h("span", { class: "klein", tid: "betrachter-zaehler" });
    const laden = h("a", { class: "knopf knopf-klein", tid: "betrachter-herunterladen" }, "Herunterladen");
    const zurMail = knopf("Zurück zur E-Mail", { class: "knopf knopf-klein", tid: "betrachter-zur-mail" });
    const zeigen = async (dok) => {
      const url = dok.url || inhaltUrl(dok.id);
      titel.textContent = dok.dateiname;
      d.el.dataset.typ = dok.mime_typ;
      d.el.dataset.dokumentId = String(dok.id);
      laden.href = dok.url ? `${dok.url}?herunterladen=true` : inhaltUrl(dok.id, true);
      laden.setAttribute("download", dok.dateiname);
      zurMail.hidden = !stapel.length;
      zurueck.hidden = vor.hidden = zaehler.hidden = dokumente.length < 2 || !!stapel.length;
      zaehler.textContent = `${i + 1} / ${dokumente.length}`;
      let ansicht;
      if (dok.mime_typ === "application/pdf") ansicht = pdfAnsicht(url, dok.dateiname);
      else if (dok.mime_typ === "message/rfc822") ansicht = await mailAnsicht(dok, (anhang) => { stapel.push(dok); zeigen(anhang); });
      else ansicht = bildAnsicht(url, dok.dateiname);
      flaeche.replaceChildren(ansicht);
      // Anhänge einer Mail sind keine eigenen Dokumente: ohne Abschnitt „Hängt an“
      if (!dok.url) flaeche.append(await buchungenAbschnitt(dok, d));
    };
    zurueck.addEventListener("click", () => { i = (i - 1 + dokumente.length) % dokumente.length; zeigen(dokumente[i]); });
    vor.addEventListener("click", () => { i = (i + 1) % dokumente.length; zeigen(dokumente[i]); });
    zurMail.addEventListener("click", () => zeigen(stapel.pop()));
    d.el.addEventListener("keydown", (e) => {
      if (e.target.closest && e.target.closest("input, textarea")) return;
      if (e.key === "ArrowLeft" && !zurueck.hidden) { e.preventDefault(); zurueck.click(); }
      if (e.key === "ArrowRight" && !vor.hidden) { e.preventDefault(); vor.click(); }
    });
    inhalt.append(h("div", { class: "betrachter-leiste" }, zurMail, zurueck, zaehler, vor, h("span", { class: "abstand" }), laden), flaeche);
    zeigen(dokumente[i]);
  }, { schliessenKnopf: "betrachter-schliessen", klasse: "dialog-betrachter", ausloeser,
    fokus: (box) => box.querySelector("[data-testid=betrachter-schliessen]") });
}

// ---------------------------------------------------------------- Abschnitt im Detailpanel

/** Abschnitt „Dokumente“ der Einzelheiten einer Buchung. */
export function detailsAbschnitt(b) {
  const belege = b.belege || [];
  const liste = belege.length ? h("ul", { class: "details-dokumente-liste" }, belege.map((d, i) => h("li", {
    tid: `details-dokument-${d.id}`, class: "details-dokument" },
  h("button", { type: "button", class: "knopf-link", tid: `dokument-ansehen-${d.id}`, title: d.dateiname,
    onclick: (e) => betrachter(belege, i, e.currentTarget) }, symbol(d.mime_typ), " ", d.dateiname),
  h("small", { class: "klein" }, " ", groesseText(d.groesse)),
  h("button", { type: "button", class: "mini-knopf", tid: `dokument-loesen-${d.id}`, "aria-label": `„${d.dateiname}“ von der Buchung lösen`,
    title: "Von dieser Buchung lösen", onclick: () => loesen(d, b.id) }, "×"))))
    : h("p", { class: "klein leer" }, "Keine Dokumente. Datei hierher ziehen oder anhängen.");
  const mobil = oberflaeche.istMobil();
  return h("div", { class: "details-dokumente", tid: "details-dokumente", "data-anzahl": String(belege.length), "data-buchung-id": String(b.id) },
    h("h3", { class: "klein" }, "Dokumente"), liste,
    h("div", { class: "knopf-leiste details-dokumente-knoepfe" },
      knopf("Datei anhängen…", { class: "knopf knopf-klein", tid: "dokument-anhaengen", onclick: () => dateiWaehlen([b.id]) }),
      mobil ? knopf("📷 Foto aufnehmen", { class: "knopf knopf-klein", tid: "dokument-foto", onclick: () => dateiWaehlen([b.id], { kamera: true }) }) : null,
      knopf("E-Mail…", { class: "knopf knopf-klein", tid: "dokument-mail", onclick: (e) => mailDialog([b.id], e.currentTarget) })));
}

async function loesen(dok, buchungId) {
  try {
    await aktion(() => api("DELETE", `/api/dokumente/${dok.id}/buchungen/${buchungId}`), {
      erfolg: (r) => (r.geloescht ? `„${dok.dateiname}“ entfernt.` : `„${dok.dateiname}“ von der Buchung gelöst.`) });
  } catch (e) { /* Meldung kam von aktion() */ }
}

// ---------------------------------------------------------------- Ziehen von Dateien

/** Dateien aus dem Betriebssystem auf Zeilen ziehen: liste = Grid, zuIds(zeile) = Ziel-Buchungen. */
export function ablageEinrichten(liste, zuIds) {
  const istDatei = (e) => e.dataTransfer && [...e.dataTransfer.types].includes("Files");
  let markiert = null;
  const markieren = (z) => {
    if (markiert === z) return;
    if (markiert) delete markiert.dataset.ablage;
    markiert = z;
    if (z) z.dataset.ablage = "ja";
  };
  liste.addEventListener("dragover", (e) => {
    if (!istDatei(e)) return;
    const z = e.target.closest && e.target.closest("[role=row][data-id]");
    markieren(z);
    if (!z) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  });
  liste.addEventListener("dragleave", (e) => { if (!liste.contains(e.relatedTarget)) markieren(null); });
  liste.addEventListener("drop", (e) => {
    if (!istDatei(e)) return;
    const z = e.target.closest && e.target.closest("[role=row][data-id]");
    markieren(null);
    if (!z) return;
    e.preventDefault();
    const dateien = [...e.dataTransfer.files];
    if (!dateien.length) { melde("hinweis", "Hier lassen sich nur Dateien ablegen."); return; }
    hochladen(zuIds(z), dateien, "upload");
  });
}
