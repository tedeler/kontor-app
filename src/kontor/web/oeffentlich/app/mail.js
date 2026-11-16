/* Mail-Blatt: abgerufene Mails und ihre Zuordnung zu erwarteten Zahlungen und Buchungen. */
import { abfrage, api, betragEl, datumText, h, oberflaeche, zeitEl, zeitText } from "./kern.js";
import { knopf } from "./ui.js";

const GRUND = { bestellung: "Bestellung", paypal: "PayPal", rueckerstattung: "Rückerstattung", manuell: "Manuell" };
const ZUSTAND = {
  offen: "erwartet, noch keine Buchung", erfuellt: "Buchung zugeordnet", guthaben: "aus Guthaben beglichen",
  storniert: "storniert", erledigt: "erledigt",
};
const FILTER = [["alle", "Alle"], ["zugeordnet", "Buchung zugeordnet"], ["erwartet", "Nur erwartet"],
  ["keine", "Nicht erkannt"]];
const PRO_SEITE = 100;

const art = (m) => {
  if (!m.zuordnung.length) return "keine";
  return m.zuordnung.some((z) => z.buchungen.length) ? "zugeordnet" : "erwartet";
};

const tausend = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");

export async function mailSeite(seite, _param, suche) {
  const p = new URLSearchParams(suche || "");
  let filter = FILTER.some(([w]) => w === p.get("filter")) ? p.get("filter") : "alle";
  let postfach = /^\d+$/.test(p.get("postfach") || "") ? p.get("postfach") : "";
  let seiteNr = /^\d+$/.test(p.get("seite") || "") ? Number(p.get("seite")) : 1;
  let gewaehlt = p.get("id");
  let stand = null;
  let gesamt = 0;
  let seiten = 1;
  let mails = [];
  let abrufText = "";
  let tastatur = false;
  let kante = "";
  let ladeNr = 0;
  const standEl = h("p", { class: "mail-stand", tid: "mail-stand" }, "Mails werden geladen…");
  const listeEl = h("div", { class: "mail-liste", tid: "mail-liste", tabindex: "0", "aria-label": "Mailliste" });
  const leseEl = h("article", { class: "karte mail-lesen", tid: "mail-lesen", tabindex: "-1",
    "aria-label": "Inhalt der ausgewählten Mail" });
  const blaetterEl = h("div", { class: "mail-blaetter", tid: "mail-blaetter" });
  const abrufKnopf = knopf("Mails abrufen", { tid: "mail-abrufen", onclick: abrufen });
  seite.append(
    h("div", { class: "seiten-kopf" }, h("h1", null, "Mail-Blatt"),
      h("div", { class: "werkzeuge" }, abrufKnopf)),
    standEl,
    h("div", { class: "chip-leiste", tid: "mail-filter" }),
    blaetterEl,
    h("div", { class: "mail-blatt" }, listeEl, leseEl));
  seite.addEventListener("keydown", (ev) => {
    if (ev.altKey || ev.ctrlKey || ev.metaKey) return;
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    if (ev.target.closest("input, textarea, select, button, a")) return;
    ev.preventDefault();
    schritt(ev.key === "ArrowDown" ? 1 : -1);
  });
  await laden();
  return { titel: "Mail-Blatt" };

  function adresseSchreiben() {
    const q = {};
    if (postfach) q.postfach = postfach;
    if (filter !== "alle") q.filter = filter;
    if (seiteNr > 1) q.seite = seiteNr;
    if (gewaehlt) q.id = gewaehlt;
    history.replaceState(null, "", "/mail" + abfrage(q));
    if (oberflaeche.urlGeaendert) oberflaeche.urlGeaendert();
  }

  async function laden() {
    const nr = ++ladeNr;
    listeEl.replaceChildren(h("p", { class: "leer", tid: "mail-laden" }, "Mails werden geladen…"));
    leseEl.replaceChildren();
    try {
      const ziel = await holen(seiteNr);
      if (nr !== ladeNr) return;
      seiteNr = ziel.seite;
      gesamt = ziel.gesamt;
      seiten = Math.max(1, Math.ceil(ziel.gesamt / PRO_SEITE));
      stand = ziel.stand;
      mails = ziel.eintraege;
      if (kante === "letzte" && mails.length) gewaehlt = String(mails[mails.length - 1].id);
      else if (kante === "erste" && mails.length) gewaehlt = String(mails[0].id);
      else if (gewaehlt && !mails.some((m) => String(m.id) === gewaehlt)) gewaehlt = "";
      if (!gewaehlt && mails.length) gewaehlt = String(mails[0].id);
      const fokus = tastatur;
      kante = "";
      tastatur = false;
      zeichnen();
      if (fokus) fokusZeile();
    } catch (e) {
      standEl.textContent = e.message || "Die Mails konnten nicht geladen werden.";
      standEl.className = "mail-stand fehler";
      listeEl.replaceChildren(h("p", { class: "leer" }, "Die Liste ist leer, weil der Abruf der Seite fehlschlug."));
    }
  }

  async function holen(nr) {
    const q = { pro_seite: PRO_SEITE, seite: nr, reihenfolge: "neueste" };
    if (postfach) q.postfach_id = Number(postfach);
    if (filter !== "alle") q.zuordnung = filter;
    return api("GET", "/api/mail/nachrichten" + abfrage(q));
  }

  function zeichnen() {
    standEl.className = "mail-stand";
    standEl.replaceChildren(...standInhalt());
    const leiste = seite.querySelector("[data-testid=mail-filter]");
    const zahlen = stand || {};
    leiste.replaceChildren(kontoWahl(), ...FILTER.map(([w, text]) => {
      const n = w === "alle" ? zahlen.gesamt : zahlen[w];
      return h("button", {
        type: "button", class: "chip" + (filter === w ? " an" : ""), "aria-pressed": filter === w ? "true" : "false",
        tid: `mail-filter-${w}`, onclick: () => { filter = w; seiteNr = 1; laden(); },
      }, n === undefined ? text : `${text} (${tausend(n)})`);
    }));
    blaetterEl.replaceChildren(
      knopf("Neuere", { tid: "mail-neuer", disabled: seiteNr <= 1, onclick: () => { seiteNr -= 1; laden(); } }),
      h("span", { tid: "mail-block" }, blockText()),
      knopf("Ältere", { tid: "mail-aelter", disabled: seiteNr >= seiten, onclick: () => { seiteNr += 1; laden(); } }));
    listeEl.replaceChildren(mails.length
      ? h("table", { class: "tabelle", tid: "mail-tabelle" },
        h("thead", null, h("tr", null, ["Empfangen", "Absender", "Betreff", "Zuordnung"].map((s) =>
          h("th", { scope: "col" }, s)))),
        h("tbody", null, mails.map(zeile)))
      : h("p", { class: "leer", tid: "mail-leer" }, leerText()));
    inhaltZeigen();
    adresseSchreiben();
  }

  function inhaltZeigen() {
    const mail = mails.find((m) => String(m.id) === gewaehlt);
    leseEl.replaceChildren(...(mail ? lesen(mail) : [h("p", { class: "leer" }, "Keine Mail ausgewählt.")]));
  }

  function auswahlSetzen(id, fokus) {
    gewaehlt = String(id);
    for (const tr of listeEl.querySelectorAll("tbody tr")) {
      const an = tr.dataset.testid === `mail-${gewaehlt}`;
      tr.classList.toggle("gewaehlt", an);
      tr.tabIndex = an ? 0 : -1;
      tr.setAttribute("aria-selected", an ? "true" : "false");
    }
    inhaltZeigen();
    adresseSchreiben();
    if (fokus) fokusZeile();
  }

  function fokusZeile() {
    const tr = listeEl.querySelector("tr.gewaehlt");
    if (!tr) return;
    tr.focus({ preventScroll: true });
    tr.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function schritt(richtung) {
    if (!mails.length) return;
    const i = mails.findIndex((m) => String(m.id) === gewaehlt);
    const n = (i < 0 ? 0 : i) + richtung;
    if (n >= 0 && n < mails.length) { auswahlSetzen(mails[n].id, true); return; }
    if (richtung > 0 && seiteNr < seiten) { tastatur = true; kante = "erste"; seiteNr += 1; laden(); }
    else if (richtung < 0 && seiteNr > 1) { tastatur = true; kante = "letzte"; seiteNr -= 1; laden(); }
  }

  function kontoWahl() {
    const kaesten = (stand && stand.postfaecher) || [];
    const wahl = h("select", { tid: "mail-konto", "aria-label": "Mailkonto" },
      h("option", { value: "" }, "Alle Konten"),
      ...kaesten.map((k) => h("option", { value: String(k.postfach_id) }, k.bezeichnung || k.adresse || "Postfach")));
    if (postfach && !kaesten.some((k) => String(k.postfach_id) === postfach)) postfach = "";
    wahl.value = postfach;
    wahl.addEventListener("change", () => { postfach = wahl.value; seiteNr = 1; gewaehlt = ""; laden(); });
    return h("label", { class: "mail-konto" }, "Konto ", wahl);
  }

  function blockText() {
    if (!gesamt) return "Keine Mails in dieser Auswahl";
    const von = (seiteNr - 1) * PRO_SEITE + 1;
    const bis = von + mails.length - 1;
    const lage = seiteNr <= 1 ? "neueste" : "älter";
    return `${tausend(von)}–${tausend(bis)} von ${tausend(gesamt)} (${lage})`;
  }

  function leerText() {
    if (gesamt === 0 && filter !== "alle") return "Keine Mail in dieser Auswahl.";
    if (!stand || !stand.postfaecher || !stand.postfaecher.length) {
      return "Keine abgerufenen Mails. Postfächer stehen unter Einstellungen.";
    }
    return "Keine abgerufenen Mails. „Mails abrufen“ holt sie aus den Postfächern.";
  }

  function standInhalt() {
    const teile = [];
    if (abrufText) teile.push(h("span", { tid: "mail-abruf-ergebnis" }, abrufText));
    if (stand && stand.postfaecher) {
      for (const p of stand.postfaecher) teile.push(h("span", { tid: `mail-postfach-${p.postfach_id}` }, postfachText(p)));
    }
    if (!teile.length) teile.push("Kein Postfach eingerichtet.");
    const aus = [];
    teile.forEach((teil, i) => {
      if (i) aus.push(" · ");
      aus.push(teil);
    });
    return aus;
  }

  function postfachText(p) {
    const name = p.bezeichnung || p.adresse || "Postfach";
    if (!p.aktiv) return `${name}: inaktiv`;
    if (p.letzter_fehler) return `${name}: letzter Abruf fehlgeschlagen (${p.letzter_fehler.meldung})`;
    if (!p.letzter_erfolg_am) return `${name}: noch nie abgerufen`;
    return `${name}: ${tausend(p.nachrichten)} Mails, zuletzt erfolgreich ${zeitText(p.letzter_erfolg_am)}`;
  }

  function zeile(m) {
    const an = String(m.id) === gewaehlt;
    const tr = h("tr", { tid: `mail-${m.id}`, tabindex: an ? "0" : "-1", "aria-selected": an ? "true" : "false",
      class: "klickbar" + (an ? " gewaehlt" : ""), "data-zuordnung": art(m) },
    zeitEl("td", m.empfangen),
    h("td", null, h("div", null, m.absender), h("small", { class: "klein" }, m.postfach)),
    h("td", null, m.betreff || "(ohne Betreff)"),
    h("td", null, zuordnungKurz(m)));
    tr.addEventListener("click", () => auswahlSetzen(m.id, false));
    tr.addEventListener("keydown", (ev) => {
      if (ev.target !== tr || ev.key !== "Enter") return;
      ev.preventDefault();
      leseEl.focus({ preventScroll: true });
    });
    return tr;
  }

  async function abrufen() {
    abrufKnopf.disabled = true;
    abrufKnopf.textContent = "Abruf läuft…";
    abrufText = "";
    standEl.className = "mail-stand";
    standEl.textContent = "Mails werden abgerufen…";
    try {
      const erg = await api("POST", "/api/mail/abruf", {});
      abrufText = abrufErgebnis(erg);
      seiteNr = 1;
      await laden();
    } catch (e) {
      standEl.textContent = e.message || "Der Abruf ist fehlgeschlagen.";
      standEl.className = "mail-stand fehler";
    } finally {
      abrufKnopf.disabled = false;
      abrufKnopf.textContent = "Mails abrufen";
    }
  }
}

function abrufErgebnis(erg) {
  const kaesten = erg.postfaecher || [];
  if (!kaesten.length) return "Abruf beendet: kein aktives Postfach.";
  return "Abruf beendet: " + kaesten.map((p) => {
    if (p.status !== "erfolgreich") return `${p.adresse}: ${p.fehler && p.fehler.meldung ? p.fehler.meldung : p.status}`;
    return `${p.adresse}: ${p.nachrichten_neu} neu, ${p.nachrichten_vorhanden} schon da`;
  }).join("; ");
}

function zuordnungKurz(m) {
  if (!m.zuordnung.length) return h("span", { class: "klein" }, "Nicht erkannt");
  return m.zuordnung.map((z) => h("div", { class: "mail-zuordnung", "data-zustand": z.ueberfaellig ? "ueberfaellig" : z.zustand },
    h("span", { class: "grund-marke" }, z.ueberfaellig ? "überfällig" : (ZUSTAND[z.zustand] || z.zustand)),
    " ", z.haendler || GRUND[z.grund] || z.grund, " ",
    betragEl("span", z.vorzeichen_betrag),
    z.buchungen.length ? h("div", { class: "klein" }, z.buchungen.map((b) => h("div", null,
      buchungsKnopf(b), b.warum ? h("div", { class: "mail-warum" }, b.warum) : null))) : null));
}

function buchungsKnopf(b) {
  const name = b.empfaenger || b.konto || "Buchung";
  return h("button", { type: "button", class: "knopf-link", tid: `mail-buchung-${b.id}`,
    onclick: (ev) => { ev.stopPropagation(); oberflaeche.zurBuchung(b.konto_id, b.id); } },
  `${datumText(b.datum)} ${name}`);
}

function lesen(m) {
  return [
    h("h2", null, m.betreff || "(ohne Betreff)"),
    h("dl", { class: "mail-kopf" },
      h("dt", null, "Von"), h("dd", null, m.absender),
      h("dt", null, "Postfach"), h("dd", null, m.postfach),
      h("dt", null, "Empfangen"), h("dd", null, zeitEl("span", m.empfangen)),
      h("dt", null, "Stand"), h("dd", null, standDerMail(m))),
    h("h3", null, "Zuordnung"),
    zuordnungAusfuehrlich(m),
    h("h3", null, "Text"),
    h("pre", { class: "mail-text", tid: "mail-text" }, m.text || ""),
  ];
}

function standDerMail(m) {
  const a = art(m);
  if (a === "keine") return "Nicht erkannt. Die Mail begründet keine erwartete Zahlung.";
  if (a === "erwartet") return "Erwartet. Eine Zahlung ist vorgemerkt, aber noch keiner Buchung zugeordnet.";
  return "Einer Buchung zugeordnet.";
}

function zuordnungAusfuehrlich(m) {
  if (!m.zuordnung.length) {
    return h("p", { tid: "mail-ohne-zuordnung" }, "Diese Mail begründet keine erwartete Zahlung.");
  }
  return h("ul", { class: "mail-zuordnung-liste", tid: "mail-zuordnungen" }, m.zuordnung.map((z) => h("li", {
    tid: `mail-erwartung-${z.erwartung_id}`, "data-zustand": z.ueberfaellig ? "ueberfaellig" : z.zustand,
  },
  h("a", { href: `/erwartet?id=${z.erwartung_id}` }, GRUND[z.grund] || z.grund, ": ", z.haendler || "ohne Händler"),
  z.kennung ? h("div", { class: "klein" }, "Kennung ", z.kennung) : null,
  h("div", null, betragEl("span", z.vorzeichen_betrag), " · ",
    z.ueberfaellig ? "überfällig" : (ZUSTAND[z.zustand] || z.zustand)),
  z.buchungen.length
    ? h("ul", null, z.buchungen.map((b) => h("li", null,
      buchungsKnopf(b), " ", betragEl("span", b.betrag),
      b.warum ? h("p", { class: "mail-warum", tid: `mail-warum-${b.id}` }, b.warum) : null,
      b.verwendungszweck ? h("span", { class: "klein" }, " ", b.verwendungszweck) : null)))
    : h("p", { class: "klein" }, "Noch keiner Buchung zugeordnet."))));
}
