/* Kontor – „Was kommt noch?“: erwartete Zahlungen aus Bestell- und Zahlungsmails (Feature mail-abgleich, D-128). */
import {
  aktion, api, betragEl, betragLesen, betragText, datumEl, datumText, h, melde, oberflaeche, tid,
} from "./kern.js";
import { bestaetigen, dialog, feld, imDialog, knopf, knopfLeiste, kontextmenue, menuePosition } from "./ui.js";
import { betrachter } from "./dokumente.js";

const GRUND = { bestellung: "Bestellung", paypal: "PayPal", rueckerstattung: "Rückerstattung", serie: "Serie",
  manuell: "Manuell" };
const ZUSTAND = { offen: "offen", erfuellt: "erfüllt", guthaben: "aus Guthaben", storniert: "storniert",
  erledigt: "erledigt" };
// Schnellfilter „Zustand“: Vorgabe ist „Offen“ (enthält die überfälligen); „Erledigt“ fasst die Abschlüsse zusammen
const ZUSTAND_CHIPS = [["offen", "Offen", ["offen"]], ["ueberfaellig", "Überfällig", ["ueberfaellig"]],
  ["erfuellt", "Erfüllt", ["erfuellt"]], ["geschlossen", "Geschlossen", ["guthaben", "storniert", "erledigt"]]];
const FAELLIG = [["", "Alle"], ["0", "Heute"], ["7", "7 Tage"], ["30", "30 Tage"]];

const plusTage = (tage) => {
  const d = new Date();
  d.setDate(d.getDate() + tage);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

function zustandLesen(suche) {
  const p = new URLSearchParams(suche || "");
  const gruende = p.getAll("grund").filter((g) => GRUND[g]);
  const zustaende = p.getAll("zustand").filter((z) => ZUSTAND_CHIPS.some((c) => c[0] === z));
  return { gruende, zustaende: zustaende.length ? zustaende : ["offen"], faellig: p.get("faellig") || "",
    suche: p.get("suche") || "" };
}

function zustandSchreiben(f) {
  const p = new URLSearchParams();
  for (const g of f.gruende) p.append("grund", g);
  if (!(f.zustaende.length === 1 && f.zustaende[0] === "offen")) for (const z of f.zustaende) p.append("zustand", z);
  if (f.faellig) p.set("faellig", f.faellig);
  if (f.suche) p.set("suche", f.suche);
  const q = p.toString();
  history.replaceState(null, "", "/erwartet" + (q ? "?" + q : ""));
  if (oberflaeche.urlGeaendert) oberflaeche.urlGeaendert();
}

function apiParameter(f) {
  const p = new URLSearchParams();
  for (const g of f.gruende) p.append("grund", g);
  for (const c of ZUSTAND_CHIPS) if (f.zustaende.includes(c[0])) for (const z of c[2]) p.append("zustand", z);
  if (f.faellig !== "") p.set("faellig_bis", plusTage(Number(f.faellig)));
  if (f.suche) p.set("suche", f.suche);
  return p.toString();
}

const chip = (text, an, tidWert, onclick) => h("button", { type: "button", class: "chip" + (an ? " an" : ""),
  "aria-pressed": an ? "true" : "false", tid: tidWert, onclick }, text);

// ------------------------------------------------------------------ Seite
export async function erwartetSeite(seite, _param, suche) {
  const f = zustandLesen(suche);
  const kopfEl = h("div", { class: "seiten-kopf" }, h("h1", null, "Was kommt noch?"),
    h("div", { class: "werkzeuge" },
      knopf("Jetzt abgleichen", { tid: "erwartet-abgleichen", onclick: abgleichen }),
      knopf("Erwartete Zahlung anlegen…", { tid: "erwartet-neu", onclick: (e) => bearbeiten(null, e.currentTarget) })));
  const filterEl = h("div", { class: "chip-leiste", tid: "erwartet-filter" });
  const sucheEl = h("input", { type: "search", tid: "erwartet-suche", placeholder: "Händler, Bestellnummer, Artikel",
    "aria-label": "Suche", value: f.suche });
  const infoEl = h("p", { tid: "erwartet-summe", class: "klein" });
  const listeEl = h("div", { tid: "erwartet-liste" });
  seite.append(kopfEl, filterEl, infoEl, listeEl);

  let zeitgeber = null;
  sucheEl.addEventListener("input", () => {
    clearTimeout(zeitgeber);
    zeitgeber = setTimeout(() => { f.suche = sucheEl.value.trim(); zustandSchreiben(f); laden(); }, 250);
  });

  function filterZeichnen() {
    const umschalten = (liste, wert) => (liste.includes(wert) ? liste.filter((x) => x !== wert) : [...liste, wert]);
    filterEl.replaceChildren(
      h("span", { class: "chip-gruppe", role: "group", "aria-label": "Grund" }, h("span", { class: "chip-titel" }, "Grund"),
        Object.entries(GRUND).map(([g, t]) => chip(t, f.gruende.includes(g), `erwartet-grund-${g}`, () => {
          f.gruende = umschalten(f.gruende, g); neu();
        }))),
      h("span", { class: "chip-gruppe", role: "group", "aria-label": "Zustand" }, h("span", { class: "chip-titel" }, "Zustand"),
        ZUSTAND_CHIPS.map(([z, t]) => chip(t, f.zustaende.includes(z), `erwartet-zustand-${z}`, () => {
          const n = umschalten(f.zustaende, z);
          f.zustaende = n.length ? n : ["offen"]; neu();
        }))),
      h("span", { class: "chip-gruppe", role: "group", "aria-label": "Fällig bis" },
        h("span", { class: "chip-titel" }, "Fällig bis"),
        FAELLIG.map(([w, t]) => chip(t, f.faellig === w, `erwartet-faellig-${w || "alle"}`, () => { f.faellig = w; neu(); }))),
      h("span", { class: "chip-gruppe" }, sucheEl));
  }
  function neu() { zustandSchreiben(f); filterZeichnen(); laden(); }

  async function laden() {
    const daten = await api("GET", "/api/erwartungen?" + apiParameter(f));
    seite.dataset.aktiv = daten.aktiv ? "ja" : "nein";
    infoEl.replaceChildren(
      daten.aktiv ? "" : h("strong", null, "Der Mail-Abgleich ist ausgeschaltet (KONTOR_MAIL_ABGLEICH=1 schaltet ihn ein). "),
      `${daten.anzahl} ${daten.anzahl === 1 ? "Eintrag" : "Einträge"}`,
      daten.ueberfaellig ? h("span", { class: "warnung" }, ` · ${daten.ueberfaellig} überfällig`) : "",
      " · noch offen: ", betragEl("strong", daten.summe_offen));
    listeEl.replaceChildren(daten.eintraege.length
      ? h("table", { class: "tabelle", tid: "erwartet-tabelle" },
        h("thead", null, h("tr", null, ["Fällig", "Grund", "Händler", "Kennung", "Betrag", "Zustand", ""].map((s) =>
          h("th", { scope: "col" }, s || h("span", { class: "nur-sr" }, "Aktionen"))))),
        h("tbody", null, daten.eintraege.map(zeile)))
      : h("p", { class: "leer", tid: "erwartet-leer" }, "Nichts erwartet – keine passenden Einträge."));
  }

  function zeile(e) {
    const mehr = knopf("…", { class: "knopf-flach", tid: `erwartung-menue-${e.id}`, "aria-haspopup": "menu",
      "aria-label": `Aktionen für ${e.haendler}`,
      onclick: (ev) => { const [x, y] = menuePosition(null, ev.currentTarget); menue(e, x, y, ev.currentTarget); } });
    const zustandText = e.ueberfaellig ? "überfällig" : (ZUSTAND[e.zustand] || e.zustand)
      + (e.zustand === "offen" && e.zugeordnet ? ` (Rest ${betragText(e.offen_betrag)})` : "");
    const tr = h("tr", { tid: `erwartung-${String(e.id).replace(/[^a-z0-9-]/gi, "-")}`, tabindex: "0", class: "klickbar" + (e.ueberfaellig ? " ueberfaellig" : ""),
      "data-zustand": e.ueberfaellig ? "ueberfaellig" : e.zustand, "data-grund": e.grund },
    datumEl("td", e.frist, { class: "e-frist" }), h("td", { class: "e-grund" }, h("span", { class: "marke grund-marke" }, GRUND[e.grund] || e.grund)),
    h("td", { class: "e-haendler" }, h("div", null, e.haendler), e.beschreibung ? h("small", { class: "klein" }, e.beschreibung) : null),
    h("td", { class: "e-kennung" }, e.kennung || e.referenz || ""),
    betragEl("td", e.vorzeichen_betrag, { class: "zahl e-betrag" }), h("td", { class: "e-zustand" }, zustandText),
    h("td", { class: "aktionen e-aktionen" }, mehr));
    tr.addEventListener("dblclick", () => (e.grund === "serie" ? oberflaeche.gehe("/wiederkehrend") : details(e.id, tr)));
    tr.addEventListener("keydown", (ev) => {
      if (ev.target !== tr) return;
      if (ev.key === "Enter") { ev.preventDefault(); if (e.grund === "serie") oberflaeche.gehe("/wiederkehrend"); else details(e.id, tr); }
      if ((ev.key === "F10" && ev.shiftKey) || ev.key === "ContextMenu") {
        ev.preventDefault(); const [x, y] = menuePosition(null, tr); menue(e, x, y, tr);
      }
    });
    tr.addEventListener("contextmenu", (ev) => { ev.preventDefault(); menue(e, ev.clientX, ev.clientY, tr); });
    return tr;
  }

  function menue(e, x, y, ausloeser) {
    if (e.grund === "serie") {  // abgeleitet aus den wiederkehrenden Buchungen: dort ansehen
      kontextmenue(x, y, [{ tid: "km-erwartung-serie", text: "Serie ansehen", tun: () => oberflaeche.gehe("/wiederkehrend") },
        { tid: "km-erwartung-konto", text: "Konto öffnen", tun: () => oberflaeche.gehe(`/konten/${e.konto_id}`) }], ausloeser);
      return;
    }
    const offen = e.zustand === "offen";
    kontextmenue(x, y, [
      { tid: "km-erwartung-details", text: "Details und Zuordnung…", tun: () => details(e.id, ausloeser) },
      { tid: "km-erwartung-bearbeiten", text: "Bearbeiten…", tun: () => bearbeiten(e, ausloeser) },
      ...(offen ? [
        { tid: "km-erwartung-erledigt", text: "Als erledigt schließen", tun: () => zustandSetzen(e, "erledigt") },
        { tid: "km-erwartung-guthaben", text: e.richtung === "eingang" ? "Verbleibt im Guthaben" : "Aus Guthaben bezahlt",
          tun: () => zustandSetzen(e, "guthaben") },
        { tid: "km-erwartung-storniert", text: "Storniert", tun: () => zustandSetzen(e, "storniert") },
      ] : []),
      ...(["guthaben", "storniert", "erledigt"].includes(e.zustand)
        ? [{ tid: "km-erwartung-oeffnen", text: "Wieder öffnen", tun: () => zustandSetzen(e, "offen") }] : []),
      ...(e.grund === "manuell" ? [{ tid: "km-erwartung-loeschen", text: "Löschen", tun: () => loeschen(e, ausloeser) }] : []),
    ], ausloeser);
  }

  async function abgleichen() {
    try {
      const r = await aktion(() => api("POST", "/api/erwartungen/abgleich", {}));
      melde("erfolg", `Abgeglichen: ${r.neu || 0} neu erkannt, ${r.zugeordnet || 0} zugeordnet.`);
    } catch (e) { melde("fehler", e.message); }
    await laden();
  }

  async function zustandSetzen(e, zustand) {
    try { await aktion(() => api("POST", `/api/erwartungen/${e.id}/zustand`, { zustand })); }
    catch (err) { melde("fehler", err.message); }
    await laden();
  }

  async function loeschen(e, ausloeser) {
    if (!await bestaetigen(`Erwartete Zahlung „${e.haendler}“ löschen?`, { ja: "Löschen", ausloeser })) return;
    try { await aktion(() => api("DELETE", `/api/erwartungen/${e.id}`)); } catch (err) { melde("fehler", err.message); }
    await laden();
  }

  // ---------------------------------------------------------------- Anlegen/Bearbeiten
  function bearbeiten(e, ausloeser) {
    dialog("erwartung-dialog", e ? "Erwartete Zahlung bearbeiten" : "Erwartete Zahlung anlegen", (inhalt, d) => {
      const richtung = h("select", { tid: "erwartung-richtung", disabled: !!e },
        h("option", { value: "ausgabe" }, "Ausgabe (Geld geht ab)"), h("option", { value: "eingang" }, "Eingang (Erstattung)"));
      if (e) richtung.value = e.richtung;
      const haendler = h("input", { tid: "erwartung-haendler", value: e ? e.haendler : "", maxlength: "200" });
      const betrag = h("input", { tid: "erwartung-betrag", inputmode: "decimal",
        value: e ? betragText(e.betrag).replace(/\s?€$/, "").replace(/\./g, "") : "" });
      const datum = h("input", { type: "date", tid: "erwartung-datum", value: e ? e.datum : "" });
      const frist = h("input", { type: "date", tid: "erwartung-frist", value: e ? e.frist : "" });
      const beschreibung = h("input", { tid: "erwartung-beschreibung", value: e ? e.beschreibung : "", maxlength: "2000" });
      const ok = knopf(e ? "Speichern" : "Anlegen", { tid: "erwartung-ok", class: "knopf knopf-haupt" });
      ok.addEventListener("click", () => imDialog(d, ok, async () => {
        const cent = betragLesen(betrag.value);
        if (cent === null || cent === "" || cent <= 0) throw new Error("Bitte einen positiven Betrag eingeben.");
        const k = { haendler: haendler.value, betrag: cent, beschreibung: beschreibung.value };
        if (datum.value) k.datum = datum.value;
        if (frist.value) k.frist = frist.value;
        await aktion(() => (e ? api("PATCH", `/api/erwartungen/${e.id}`, k)
          : api("POST", "/api/erwartungen", { ...k, richtung: richtung.value })), { danach: () => d.schliessen(true) });
        await laden();
      }));
      inhalt.append(feld("Richtung", richtung), feld("Händler / Zahlungsempfänger", haendler),
        feld("Betrag (Bankanteil)", betrag), feld("Datum", datum, "leer: heute"),
        feld("Fällig bis", frist, "leer: Datum + Frist aus den Einstellungen"), feld("Beschreibung", beschreibung),
        knopfLeiste(ok, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
    }, { ausloeser });
  }

  // ---------------------------------------------------------------- Details, Zuordnung
  async function details(id, ausloeser) {
    let e;
    try { e = await api("GET", `/api/erwartungen/${id}`); } catch (err) { melde("fehler", err.message); return; }
    const d = dialog("erwartung-details", `${GRUND[e.grund] || e.grund}: ${e.haendler}`, (inhalt) => {
      inhalt.append(h("dl", { class: "angaben" },
        h("dt", null, "Betrag"), h("dd", null, betragEl("span", e.vorzeichen_betrag),
          e.guthaben ? ` (gesamt ${betragText(e.gesamt)}, davon ${betragText(e.guthaben)} aus Guthaben)` : ""),
        h("dt", null, "Datum / fällig bis"), h("dd", null, `${datumText(e.datum)} / ${datumText(e.frist)}`),
        h("dt", null, "Zustand"), h("dd", { tid: "erwartung-zustand" }, e.ueberfaellig ? "überfällig" : ZUSTAND[e.zustand]),
        e.kennung ? [h("dt", null, "Kennung"), h("dd", null, e.kennung)] : null,
        e.referenz ? [h("dt", null, "Bestellnummer beim Händler"), h("dd", null, e.referenz)] : null,
        e.beschreibung ? [h("dt", null, "Artikel / Beschreibung"), h("dd", null, e.beschreibung)] : null));
      if (e.mail_eintraege.length) {
        inhalt.append(h("h3", null, "Mails"), h("ul", { tid: "erwartung-mails" }, e.mail_eintraege.map((m) =>
          h("li", null, `${datumText(m.empfangen)} – ${m.betreff}`, m.spiegel_id ? "" : " (nicht mehr im Postfach-Spiegel)"))));
      }
      const buchungen = h("ul", { tid: "erwartung-buchungen" }, e.buchungen.map((b) => h("li", null,
        `${datumText(b.datum)} · ${b.konto} · `, betragEl("span", b.betrag), ` · ${b.empfaenger || b.verwendungszweck || ""} `,
        knopf("Zeigen", { class: "knopf-flach", onclick: () => { d.schliessen(null); oberflaeche.gehe(`/konten/${b.konto_id}?buchung=${b.id}`); } }),
        knopf("Lösen", { class: "knopf-flach", tid: `erwartung-loesen-${b.id}`, onclick: async () => {
          try { await aktion(() => api("DELETE", `/api/erwartungen/${e.id}/buchungen/${b.id}`)); } catch (err) { d.fehler(err.message); return; }
          d.schliessen(null); await laden(); details(e.id, ausloeser);
        } }))));
      inhalt.append(h("h3", null, "Zugeordnete Buchungen"), e.buchungen.length ? buchungen : h("p", { class: "leer" }, "Noch keine."));
      if (e.dokument_ids.length) {
        inhalt.append(knopf(`Belege ansehen (${e.dokument_ids.length})`, { tid: "erwartung-belege", onclick: async (ev) => {
          const liste = [];
          for (const did of e.dokument_ids) { try { liste.push(await api("GET", `/api/dokumente/${did}`)); } catch { /* entfernt */ } }
          if (liste.length) betrachter(liste, 0, ev.currentTarget);
        } }));
      }
      if (e.zustand === "offen") {
        const kandEl = h("div", { tid: "erwartung-kandidaten" }, h("p", { class: "klein" }, "Kandidaten werden gesucht…"));
        inhalt.append(h("h3", null, "Passende Buchungen"), kandEl);
        api("GET", `/api/erwartungen/${e.id}/kandidaten`).then((k) => {
          kandEl.replaceChildren(k.eintraege.length ? h("ul", null, k.eintraege.map((b) => h("li", { tid: `kandidat-${b.id}` },
            `${datumText(b.datum)} · ${b.konto} · `, betragEl("span", b.betrag), ` · ${b.empfaenger || ""} ${b.verwendungszweck || ""} `,
            b.kennung_passt ? h("span", { class: "marke" }, "Kennung") : null,
            b.betrag_gleich ? h("span", { class: "marke" }, "Betrag") : null,
            knopf("Zuordnen", { class: "knopf knopf-haupt", tid: `kandidat-zuordnen-${b.id}`, onclick: async () => {
              try { await aktion(() => api("POST", `/api/erwartungen/${e.id}/buchungen`, { buchung_ids: [b.id] })); }
              catch (err) { d.fehler(err.message); return; }
              melde("erfolg", "Zugeordnet; die Mails hängen jetzt an der Buchung.");
              d.schliessen(true); await laden();
            } }))))
            : h("p", { class: "leer" }, "Keine passende Bankbuchung gefunden (gleicher Betrag oder Kennung, bis 45 Tage nach dem Datum)."));
        }).catch((err) => kandEl.replaceChildren(h("p", { class: "dialog-fehler" }, err.message)));
      }
      inhalt.append(knopfLeiste(knopf("Schließen", { onclick: () => d.schliessen(null) })));
    }, { ausloeser, klasse: "dialog-breit", schliessenKnopf: "erwartung-details-schliessen" });
    return d;
  }

  filterZeichnen();
  await laden();
  const p = new URLSearchParams(suche || "");
  if (p.get("id")) details(Number(p.get("id")), tid("erwartet-tabelle"));
  return { titel: "Was kommt noch?", aktualisieren: laden };
}
