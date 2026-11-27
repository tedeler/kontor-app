/* Kontor – Kategorienbaum (oberflaeche.md 13.1), Kontextmenü für Konten (8.2), Ziehen (10) und Gesten (16.4). */
import { aktion, api, baumFolge, betragEl, betragText, datumText, h, kontoNach, melde, oberflaeche, stamm } from "./kern.js";
import { kategorienZusammenfuehren, kontextmenue, kontoDialog, kontoEinstellungen, kontoLoeschen, menuePosition,
  zielAuswahl } from "./ui.js";

// ------------------------------------------------------------------ Kontextmenü für Konten und Kategorien (8.2)
export function kontoMenue(konto, x, y, ausloeser, optionen) {
  const o = optionen || {};
  const istKategorie = konto.art === "aufwand" || konto.art === "ertrag";
  // Mehrfachauswahl im Kategorienbaum: Zusammenführen wirkt auf alle markierten, wenn der Eintrag dazugehört (D-126)
  const markierte = o.markierte ? o.markierte() : [];
  const quellen = markierte.some((k) => k.id === konto.id) ? markierte : [konto];
  kontextmenue(x, y, [
    istKategorie ? { tid: "km-kategorie-zusammenfuehren",
      text: quellen.length > 1 ? `${quellen.length} Kategorien zusammenführen in…` : "Zusammenführen in…",
      tun: () => kategorienZusammenfuehren(quellen, ausloeser) } : null,
    { tid: "km-konto-oeffnen", text: "Öffnen", tun: () => oberflaeche.gehe(`/konten/${konto.id}`) },
    { tid: "km-konto-umbenennen", text: "Umbenennen…", tun: () => umbenennen(konto, o.namensZelle ? o.namensZelle() : null) },
    { tid: "km-konto-einstellungen", text: "Einstellungen…", tun: () => kontoEinstellungen(konto, ausloeser) },
    { tid: "km-konto-unterkonto", text: "Unterkonto anlegen…",
      tun: () => kontoDialog({ titel: `Unterkonto von „${konto.name}“`, art: konto.art, eltern_id: konto.id }, ausloeser) },
    { tid: "km-konto-verschieben", text: "Verschieben nach…", tun: () => verschieben(konto, ausloeser) },
    { tid: "km-konto-loeschen", text: "Löschen…", tun: () => kontoLoeschen(konto, ausloeser) },
  ].filter(Boolean), ausloeser);
}

async function verschieben(konto, ausloeser) {
  const w = await zielAuswahl(konto, ausloeser);
  if (!w || (w.eltern_id ?? null) === (konto.eltern_id ?? null)) return;
  try {
    await aktion(() => api("PATCH", `/api/konten/${konto.id}`, { eltern_id: w.eltern_id }),
      { erfolg: `„${konto.name}“ verschoben.` });
  } catch (e) { /* gemeldet */ }
}

/** Eingabe `umbenennen-eingabe` an Ort und Stelle (Enter → PATCH, Esc bricht ab). */
export function umbenennen(konto, zelle) {
  const ort = zelle && zelle.isConnected ? zelle : null;
  const eingabe = h("input", { type: "text", tid: "umbenennen-eingabe", value: konto.name, maxlength: "200",
    "aria-label": `Neuer Name für ${konto.name}`, class: "umbenennen" });
  let fertig = false;
  const alt = ort ? [...ort.childNodes] : null;
  const zurueck = () => {
    if (ort) ort.replaceChildren(...alt);
    else eingabe.closest(".umbenennen-huelle")?.remove();
  };
  async function uebernehmen() {
    if (fertig) return;
    fertig = true;
    const neu = eingabe.value.trim();
    zurueck();
    if (!neu || neu === konto.name) return;
    try {
      await aktion(() => api("PATCH", `/api/konten/${konto.id}`, { name: neu }), { erfolg: `Umbenannt in „${neu}“.` });
    } catch (e) { /* gemeldet */ }
  }
  eingabe.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") { e.preventDefault(); uebernehmen(); }
    else if (e.key === "Escape") { e.preventDefault(); fertig = true; zurueck(); }
  });
  eingabe.addEventListener("blur", () => { if (!fertig) { fertig = true; zurueck(); } });
  for (const t of ["click", "dblclick", "pointerdown", "contextmenu"]) eingabe.addEventListener(t, (e) => e.stopPropagation());
  if (ort) ort.replaceChildren(eingabe);
  else document.body.append(h("div", { class: "umbenennen-huelle" }, eingabe));
  eingabe.focus();
  eingabe.select();
}

// ------------------------------------------------------------------ Ziehen mit der Maus (10)
/**
 * Zeigerbasiertes Ziehen (echte Mausereignisse, Schwelle 4 px). `ziel(x, y)` liefert {el, annehmen} oder null;
 * `ablegen(ziel)` wirkt. Danach wird der folgende Klick unterdrückt.
 */
export function ziehbar(el, optionen) {
  el.addEventListener("pointerdown", (ev) => {
    if (ev.pointerType !== "mouse" || ev.button !== 0) return;
    if (ev.target.closest("button, input, select, a, textarea, [data-nicht-ziehen]")) return;
    const quelle = optionen.quelle(ev);
    if (!quelle) return;
    const x0 = ev.clientX;
    const y0 = ev.clientY;
    let laeuft = false;
    let geist = null;
    let aktuell = null;
    const markieren = (z) => {
      if (aktuell && aktuell.el !== (z && z.el)) delete aktuell.el.dataset.ablage;
      aktuell = z;
      if (z) z.el.dataset.ablage = z.annehmen ? "ja" : "nein";
    };
    const bewegen = (e) => {
      if (!laeuft) {
        if (Math.abs(e.clientX - x0) < 4 && Math.abs(e.clientY - y0) < 4) return;
        laeuft = true;
        try { el.setPointerCapture(ev.pointerId); } catch (f) { /* ohne Erfassung */ }
        if (optionen.start) optionen.start(quelle);
        geist = h("div", { class: "zieh-geist", "aria-hidden": "true" }, optionen.text(quelle));
        document.body.append(geist);
        document.documentElement.classList.add("zieht");
      }
      e.preventDefault();
      geist.style.left = e.clientX + 12 + "px";
      geist.style.top = e.clientY + 8 + "px";
      markieren(optionen.ziel(e.clientX, e.clientY, quelle));
    };
    const ende = (e) => {
      document.removeEventListener("pointermove", bewegen, true);
      document.removeEventListener("pointerup", ende, true);
      document.removeEventListener("pointercancel", ende, true);
      if (!laeuft) return;
      const z = e.type === "pointerup" ? optionen.ziel(e.clientX, e.clientY, quelle) : null;
      markieren(null);
      geist.remove();
      document.documentElement.classList.remove("zieht");
      if (optionen.ende) optionen.ende(quelle);
      klickUnterdruecken();
      if (z && z.annehmen) optionen.ablegen(quelle, z);
    };
    document.addEventListener("pointermove", bewegen, true);
    document.addEventListener("pointerup", ende, true);
    document.addEventListener("pointercancel", ende, true);
  });
}

function klickUnterdruecken() {
  const weg = (e) => { e.stopPropagation(); e.preventDefault(); };
  window.addEventListener("click", weg, true);
  setTimeout(() => window.removeEventListener("click", weg, true), 0);
}

// ------------------------------------------------------------------ Lange Berührung (16.4)
/** Erkennt lange Berührung (≥ 500 ms, ≤ 10 px) auf Elementen unter `wurzel`, die `finden(ziel)` liefert. */
export function langeBeruehrung(wurzel, finden, wirkung) {
  let t = null;
  wurzel.addEventListener("touchstart", (ev) => {
    if (ev.touches.length !== 1) return;
    const el = finden(ev.target);
    if (!el) return;
    const p = ev.touches[0];
    t = { el, x: p.clientX, y: p.clientY, timer: setTimeout(() => { t.ausgeloest = true; wirkung(t.el, t.x, t.y); }, 500) };
  }, { passive: true });
  wurzel.addEventListener("touchmove", (ev) => {
    if (!t) return;
    const p = ev.touches[0];
    if (Math.hypot(p.clientX - t.x, p.clientY - t.y) > 10) { clearTimeout(t.timer); t = null; }
  }, { passive: true });
  const ende = (ev) => {
    if (!t) return;
    clearTimeout(t.timer);
    if (t.ausgeloest && ev.cancelable) ev.preventDefault();      // kein Tippen nach der langen Berührung
    t = null;
  };
  wurzel.addEventListener("touchend", ende);
  wurzel.addEventListener("touchcancel", ende);
}

// ------------------------------------------------------------------ Kategorienbaum (13.1)
const zugeklappt = new Set();
const markiert = new Set(); // Mehrfachauswahl im Kategorienbaum (D-126), bleibt beim Neuzeichnen erhalten

/** Alle Kategorien mit Unterkategorien auf- (`zu` = false) oder zuklappen (D-310). */
export function alleKlappen(zu) {
  zugeklappt.clear();
  if (!zu) return;
  const eltern = new Set(stamm.konten.map((k) => k.eltern_id).filter(Boolean));
  for (const k of stamm.konten) if ((k.art === "aufwand" || k.art === "ertrag") && eltern.has(k.id)) zugeklappt.add(k.id);
}

// D-310: Farbton je Wurzelkategorie (Unterkategorien erben ihn); fest nach der ID, damit er beim Sortieren bleibt
const TOENE = 8;

/** Name mit hervorgehobenem Suchtreffer (nur Textknoten, nie HTML). */
function nameMitTreffer(name, suche) {
  const i = suche ? name.toLocaleLowerCase("de").indexOf(suche) : -1;
  if (i < 0) return name;
  return [name.slice(0, i), h("mark", null, name.slice(i, i + suche.length)), name.slice(i + suche.length)];
}

/** Kleiner Verlauf (zwölf Monate) als SVG-Linie; Werte in Cent, nur zum Zeichnen. */
function verlaufEl(werte, monate) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "kat-verlauf");
  svg.setAttribute("viewBox", "0 0 66 20");
  svg.setAttribute("aria-hidden", "true");
  if (!werte || !werte.some((w) => w !== 0)) { svg.classList.add("leer"); return svg; }
  const max = Math.max(...werte, 0);
  const min = Math.min(...werte, 0);
  const spanne = max - min || 1;
  const punkte = werte.map((w, i) => [3 + i * 5.45, 17 - ((w - min) * 14) / spanne]);
  const flaeche = document.createElementNS(ns, "path");
  flaeche.setAttribute("d", `M${punkte[0][0]},17 ` + punkte.map(([x, y]) => `L${x.toFixed(1)},${y.toFixed(1)}`).join(" ")
    + ` L${punkte[punkte.length - 1][0].toFixed(1)},17 Z`);
  flaeche.setAttribute("class", "kat-verlauf-flaeche");
  const linie = document.createElementNS(ns, "polyline");
  linie.setAttribute("points", punkte.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" "));
  linie.setAttribute("class", "kat-verlauf-linie");
  const [lx, ly] = punkte[punkte.length - 1];
  const punkt = document.createElementNS(ns, "circle");
  punkt.setAttribute("cx", lx.toFixed(1));
  punkt.setAttribute("cy", ly.toFixed(1));
  punkt.setAttribute("r", "1.8");
  punkt.setAttribute("class", "kat-verlauf-punkt");
  const titel = document.createElementNS(ns, "title");
  titel.textContent = monate ? monate.map((m, i) => `${m.slice(5)}/${m.slice(2, 4)}: ${betragText(werte[i])}`).join("\n") : "";
  svg.append(titel, flaeche, linie, punkt);
  return svg;
}

/**
 * Baut den Kategorienbaum (`kategorienbaum`, Rolle `tree`) aus stamm.konten. Jeder Eintrag ist genau eine Zeile
 * hoch; die Unterkategorien stehen im DOM innerhalb des Eintrags (role=group), werden aber darunter angeordnet
 * (der Eintrag reserviert ihren Platz mit einem Außenabstand). So liegt die Mitte eines Eintrags auf seiner eigenen
 * Zeile, nicht auf einer Unterkategorie.
 * optionen.buchungsZiel: true → Einträge nehmen gezogene Buchungen an (Kontoansicht).
 * Kategorienseite (D-310): optionen.werte (Map id → {summe, anzahl, letzte, verlauf}), optionen.monate,
 * optionen.summen ({aufwand, ertrag}), optionen.suche, optionen.nachBetrag; jede Zeile bekommt dann Knöpfe zum Öffnen
 * und für das Kontextmenü. Ohne diese Optionen bleibt der Baum wie im Seitenbereich der Kontoansicht.
 */
export function kategorienBaum(optionen) {
  const o = optionen || {};
  const werte = o.werte || null;
  const suche = (o.suche || "").trim().toLocaleLowerCase("de");
  const baum = h("div", { role: "tree", tid: "kategorienbaum", class: "baum" + (werte ? " baum-uebersicht" : ""),
    "aria-label": "Kategorien", "aria-multiselectable": "true" });
  const eintraege = new Map();
  for (const [art, titel] of [["aufwand", "Ausgaben"], ["ertrag", "Einnahmen"]]) {
    const konten = stamm.konten.filter((k) => k.art === art);
    const gruppe = h("div", { role: "group", class: `baum-gruppe baum-gruppe-${art}`, "aria-label": titel });
    const gesamt = werte && o.summen ? o.summen[art] || 0 : 0;
    const kopf = h("div", { class: "baum-gruppenkopf", tid: `kategorien-gruppe-${art}`, "data-gruppe": art },
      werte ? [h("span", { class: "baum-gruppenname" }, titel),
        h("span", { class: "baum-gruppenzahl klein" }, konten.length === 1 ? "1 Kategorie" : `${konten.length} Kategorien`),
        betragEl("span", gesamt, { class: "baum-gruppensumme", tid: `kategorien-summe-${art}` })] : titel);
    gruppe.append(kopf);
    const folge = baumFolge(konten);
    const kinderVon = new Map();
    for (const f of folge) {
      const e = f.konto.eltern_id && konten.some((k) => k.id === f.konto.eltern_id) ? f.konto.eltern_id : 0;
      if (!kinderVon.has(e)) kinderVon.set(e, []);
      kinderVon.get(e).push(f);
    }
    const summe = (k) => (werte && werte.get(k.id) ? werte.get(k.id).summe : 0);
    // Balken: die größte Wurzelkategorie füllt ihn ganz; der Anteil an der Gruppe steht im Titel
    const groesste = werte ? Math.max(0, ...konten.map((k) => summe(k))) : 0;
    if (o.nachBetrag && werte) {
      for (const liste of kinderVon.values()) liste.sort((a, b) => summe(b.konto) - summe(a.konto));
    }
    // Suche (D-310): Treffer, ihre Vorfahren und ihre Unterkategorien bleiben sichtbar, alles aufgeklappt
    let zeigen = null;
    if (suche) {
      zeigen = new Set();
      const treffer = (k) => k.name.toLocaleLowerCase("de").includes(suche);
      const ab = (f, vorfahrTrifft) => {
        const selbst = vorfahrTrifft || treffer(f.konto);
        let irgendwas = selbst;
        for (const c of kinderVon.get(f.konto.id) || []) irgendwas = ab(c, selbst) || irgendwas;
        if (irgendwas) zeigen.add(f.konto.id);
        return irgendwas;
      };
      for (const f of kinderVon.get(0) || []) ab(f, false);
    }
    const bauen = (f, ton) => {
      const k = f.konto;
      const kinder = (kinderVon.get(k.id) || []).filter((c) => !zeigen || zeigen.has(c.konto.id));
      const offen = kinder.length > 0 && (!!zeigen || !zugeklappt.has(k.id));
      const zeile = h("span", { class: "baum-zeile", stil: { "--stufe": String(f.ebene - 1) } },
        kinder.length ? h("span", { class: "baum-schalter", "aria-hidden": "true", "data-nicht-ziehen": "" }, offen ? "▾" : "▸")
          : h("span", { class: "baum-schalter leer", "aria-hidden": "true" }),
        werte ? h("span", { class: "kat-punkt", "aria-hidden": "true" }) : null,
        h("span", { class: "baum-name" }, werte ? nameMitTreffer(k.name, suche) : k.name));
      if (werte) {
        const w = werte.get(k.id) || { summe: 0, anzahl: 0, letzte: null, verlauf: null };
        const anteil = gesamt > 0 && w.summe > 0 ? Math.min(1000, Math.round((w.summe * 1000) / gesamt)) : 0;
        const balken = groesste > 0 && w.summe > 0 ? Math.min(1000, Math.round((w.summe * 1000) / groesste)) : 0;
        zeile.title = [`${w.anzahl === 1 ? "1 Buchung" : `${w.anzahl} Buchungen`} im Zeitraum`,
          anteil ? `${(anteil / 10).toLocaleString("de-DE")} % der ${titel}` : null,
          w.letzte ? `zuletzt am ${datumText(w.letzte)}` : "noch keine Buchung"].filter(Boolean).join(" · ");
        const oeffnen = h("button", { type: "button", class: "kat-knopf", tabindex: "-1", tid: `kategorie-oeffnen-${k.id}`,
          "aria-label": `Kontoblatt ${k.name} öffnen`, title: "Kontoblatt öffnen", "data-nicht-ziehen": "" }, "→");
        const menue = h("button", { type: "button", class: "kat-knopf", tabindex: "-1", tid: `kategorie-menue-${k.id}`,
          "aria-label": `Aktionen für ${k.name}`, "aria-haspopup": "menu", title: "Aktionen", "data-nicht-ziehen": "" }, "⋯");
        const menueOeffnen = () => {
          const [x, y] = menuePosition(null, menue);
          kontoMenue(k, x, y, menue, { namensZelle: () => eintraege.get(k.id).querySelector(".baum-name"), markierte });
        };
        for (const [b, tun] of [[oeffnen, () => oberflaeche.gehe(`/konten/${k.id}`)], [menue, menueOeffnen]]) {
          b.addEventListener("click", (e) => { e.stopPropagation(); tun(); });
          b.addEventListener("dblclick", (e) => e.stopPropagation());
        }
        zeile.append(
          h("span", { class: "kat-anzahl klein", "aria-hidden": "true" }, w.anzahl ? `${w.anzahl}×` : ""),
          verlaufEl(w.verlauf, o.monate),
          h("span", { class: "kat-anteil", "aria-hidden": "true" }, h("span", { stil: { width: `${balken / 10}%` } })),
          betragEl("span", w.summe, { class: "kat-betrag" + (w.anzahl || w.summe ? "" : " kat-null"), tid: `kategorie-summe-${k.id}` }),
          h("span", { class: "kat-aktionen" }, oeffnen, menue));
      }
      const el = h("div", { role: "treeitem", tid: `kategorie-${k.id}`, class: "baum-eintrag", "aria-level": String(f.ebene),
        "aria-label": k.name, "aria-expanded": kinder.length ? String(offen) : null, tabindex: "-1",
        "data-konto-id": String(k.id), "data-klasse": art, "aria-selected": markiert.has(k.id) ? "true" : "false",
        "data-ton": werte ? String(ton) : null }, zeile);
      let unter = 0;
      if (kinder.length) {
        const grp = h("div", { role: "group", class: "baum-kinder", hidden: !offen });
        for (const c of kinder) {
          const [kel, n] = bauen(c, ton);
          grp.append(kel);
          unter += n;
        }
        el.append(grp);
        zeile.querySelector(".baum-schalter").addEventListener("click", (e) => {
          e.stopPropagation();
          if (zugeklappt.has(k.id)) zugeklappt.delete(k.id); else zugeklappt.add(k.id);
          if (o.neuZeichnen) o.neuZeichnen();
        });
      }
      const sichtbar = offen ? unter : 0;
      el.style.setProperty("--nach", String(sichtbar));
      eintraege.set(k.id, el);
      return [el, sichtbar + 1];
    };
    const wurzeln = (kinderVon.get(0) || []).filter((f) => !zeigen || zeigen.has(f.konto.id));
    for (const f of wurzeln) gruppe.append(bauen(f, f.konto.id % TOENE)[0]);
    if (werte && !wurzeln.length) {
      gruppe.append(h("p", { class: "baum-leer leer" }, suche ? "Keine Treffer." : `Noch keine ${titel}-Kategorie.`));
    }
    baum.append(gruppe);
  }
  const erster = baum.querySelector('[role="treeitem"]');
  if (erster) erster.tabIndex = 0;

  const eintragVon = (ziel) => ziel && ziel.closest && ziel.closest('[role="treeitem"]');
  const kontoVon = (el) => kontoNach(Number(el.dataset.kontoId));

  // Fokus und Tastatur (roving tabindex)
  const sichtbare = () => [...baum.querySelectorAll('[role="treeitem"]')].filter((e) => !e.closest("[hidden]"));
  function fokus(el) {
    for (const e of baum.querySelectorAll('[role="treeitem"][tabindex="0"]')) e.tabIndex = -1;
    el.tabIndex = 0;
    el.focus();
  }
  // Mehrfachauswahl wie im Dateimanager: Strg/⌘ schaltet um, Umschalt markiert einen Bereich (D-126)
  let anker = null;
  const auswahlZeigen = () => {
    for (const el of baum.querySelectorAll('[role="treeitem"]')) {
      el.setAttribute("aria-selected", markiert.has(Number(el.dataset.kontoId)) ? "true" : "false");
    }
  };
  const markieren = (el, e) => {
    const id = Number(el.dataset.kontoId);
    if (e.shiftKey && anker !== null) {
      const s = sichtbare();
      const a = s.findIndex((x) => Number(x.dataset.kontoId) === anker);
      const b = s.indexOf(el);
      if (a >= 0 && b >= 0) {
        if (!e.ctrlKey && !e.metaKey) markiert.clear();
        for (const x of s.slice(Math.min(a, b), Math.max(a, b) + 1)) markiert.add(Number(x.dataset.kontoId));
      }
    } else if (e.ctrlKey || e.metaKey || e.key === " ") {
      if (markiert.has(id)) markiert.delete(id); else markiert.add(id);
      anker = id;
    } else {
      markiert.clear();
      markiert.add(id);
      anker = id;
    }
    auswahlZeigen();
  };
  const markierte = () => [...markiert].map((id) => kontoNach(id)).filter(Boolean);
  baum.addEventListener("click", (e) => {
    const el = eintragVon(e.target);
    if (!el || e.target.closest(".baum-schalter")) return;
    fokus(el);
    markieren(el, e);
  });
  baum.addEventListener("dblclick", (e) => {
    const el = eintragVon(e.target);
    if (el && !e.target.closest(".baum-schalter")) oberflaeche.gehe(`/konten/${el.dataset.kontoId}`);
  });
  baum.addEventListener("keydown", (e) => {
    const el = eintragVon(e.target);
    if (!el || e.target !== el) return;
    const s = sichtbare();
    const i = s.indexOf(el);
    if (e.key === "ArrowDown" && i < s.length - 1) { e.preventDefault(); fokus(s[i + 1]); }
    else if (e.key === "ArrowUp" && i > 0) { e.preventDefault(); fokus(s[i - 1]); }
    else if (e.key === "Home") { e.preventDefault(); fokus(s[0]); }
    else if (e.key === "End") { e.preventDefault(); fokus(s[s.length - 1]); }
    else if (e.key === "ArrowRight" && el.getAttribute("aria-expanded") === "false") {
      e.preventDefault(); zugeklappt.delete(Number(el.dataset.kontoId)); if (o.neuZeichnen) o.neuZeichnen();
    } else if (e.key === "ArrowLeft" && el.getAttribute("aria-expanded") === "true") {
      e.preventDefault(); zugeklappt.add(Number(el.dataset.kontoId)); if (o.neuZeichnen) o.neuZeichnen();
    } else if (e.key === "Enter") { e.preventDefault(); oberflaeche.gehe(`/konten/${el.dataset.kontoId}`); }
    else if (e.key === " ") { e.preventDefault(); markieren(el, e); }
    else if (e.key === "Escape" && markiert.size) { e.preventDefault(); markiert.clear(); auswahlZeigen(); }
    else if (e.key === "F2") { e.preventDefault(); umbenennen(kontoVon(el), el.querySelector(".baum-name")); }
    else if ((e.key === "F10" && e.shiftKey) || e.key === "ContextMenu") {
      e.preventDefault();
      const [x, y] = menuePosition(null, el.querySelector(".baum-zeile"));
      kontoMenue(kontoVon(el), x, y, el, { namensZelle: () => el.querySelector(".baum-name"), markierte });
    }
  });
  baum.addEventListener("contextmenu", (e) => {
    const el = eintragVon(e.target);
    if (!el) return;
    e.preventDefault();
    fokus(el);
    kontoMenue(kontoVon(el), e.clientX, e.clientY, el, { namensZelle: () => el.querySelector(".baum-name"), markierte });
  });
  langeBeruehrung(baum, eintragVon, (el, x, y) => {
    fokus(el);
    kontoMenue(kontoVon(el), x, y, el, { namensZelle: () => el.querySelector(".baum-name"), markierte });
  });

  // Umsortieren per Drag and Drop (10, E-144)
  const zielAn = (x, y, quelle) => {
    const t = document.elementFromPoint(x, y);
    if (!t || !baum.contains(t)) return null;
    const kopf = t.closest("[data-gruppe]");
    if (kopf) return { el: kopf, eltern_id: null, annehmen: kopf.dataset.gruppe === quelle.art };
    const el = eintragVon(t);
    if (!el) return null;
    const zielId = Number(el.dataset.kontoId);
    const ok = el.dataset.klasse === quelle.art && !quelle.el.contains(el);
    return { el, eltern_id: zielId, annehmen: ok };
  };
  ziehbar(baum, {
    quelle: (ev) => {
      const el = eintragVon(ev.target);
      if (!el || ev.target.closest(".baum-schalter")) return null;
      const k = kontoVon(el);
      return k ? { el, konto: k, art: el.dataset.klasse } : null;
    },
    text: (q) => q.konto.name,
    ziel: (x, y, q) => (o.buchungsZielAktiv && o.buchungsZielAktiv() ? null : zielAn(x, y, q)),
    ablegen: async (q, z) => {
      if ((q.konto.eltern_id ?? null) === (z.eltern_id ?? null)) return;
      try {
        await aktion(() => api("PATCH", `/api/konten/${q.konto.id}`, { eltern_id: z.eltern_id }),
          { erfolg: `„${q.konto.name}“ verschoben.` });
      } catch (e) { /* gemeldet */ }
    },
  });

  /** Ziel für gezogene Buchungen (Kontoansicht): nur Kategorieeinträge. */
  baum.buchungsZiel = (x, y) => {
    const t = document.elementFromPoint(x, y);
    const el = t && baum.contains(t) ? eintragVon(t) : null;
    return el ? { el, kategorie_id: Number(el.dataset.kontoId), annehmen: true } : null;
  };
  return baum;
}

export function meldeUnbekannt() { melde("fehler", "Das Konto gibt es nicht mehr."); }
