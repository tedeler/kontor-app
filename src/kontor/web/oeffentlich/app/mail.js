/* Mail-Blatt: abgerufene Mails und ihre Zuordnung zu erwarteten Zahlungen und Buchungen. */
import { BESTAND, abfrage, aktion, api, betragEl, datumText, h, kontoNach, nameAnzeige, oberflaeche, zeitEl, zeitText } from "./kern.js";
import { bestaetigen, dialog, feld, imDialog, knopf, knopfLeiste } from "./ui.js";

const GRUND = { bestellung: "Bestellung", paypal: "PayPal", rueckerstattung: "Rückerstattung", manuell: "Manuell" };
const ZUSTAND = {
  offen: "erwartet, noch keine Buchung", erfuellt: "Buchung zugeordnet", guthaben: "aus Guthaben beglichen",
  storniert: "storniert", erledigt: "erledigt",
};
const FILTER = [["alle", "Alle"], ["zugeordnet", "Buchung zugeordnet"], ["erwartet", "Nur erwartet"],
  ["keine", "Nicht erkannt"]];
const PRO_SEITE = 100;

const haengt = (m) => m.angehaengt || [];   // D-208: über die Bestellnummer an Buchungen gehängt
const art = (m) => {
  if (haengt(m).length) return "zugeordnet";
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
  let suchtext = (p.get("suche") || "").trim();
  let suchUhr = null;
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
  const abrufKnopf = knopf("Mails abrufen", { tid: "mail-abrufen", onclick: () => abrufen(false) });
  // D-246: das ganze Postfach erneut als Kopfzeilen holen (nur mit KONTOR_MAIL_NUR_KOEPFE=1 sichtbar)
  const alleKnopf = knopf("Alle Kopfzeilen neu abrufen …", { tid: "mail-alle-koepfe", onclick: (ev) => alleAbrufen(ev.currentTarget) });
  alleKnopf.hidden = true;
  const fortschrittEl = h("div", { class: "mail-fortschritt", tid: "mail-fortschritt", role: "status", "aria-live": "polite" });
  fortschrittEl.hidden = true;
  // D-226: einfache Suche in Absender, Betreff und Text (alle Wörter müssen vorkommen)
  const suchFeld = h("input", { type: "search", tid: "mail-suche", class: "mail-suche", placeholder: "Absender, Betreff, Text …",
    "aria-label": "Mails durchsuchen", value: suchtext, maxlength: "200" });
  const suchen = () => {
    const neu = suchFeld.value.trim();
    if (neu === suchtext) return;
    suchtext = neu; seiteNr = 1; gewaehlt = ""; laden();
  };
  suchFeld.addEventListener("input", () => { clearTimeout(suchUhr); suchUhr = setTimeout(suchen, 300); });
  suchFeld.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { clearTimeout(suchUhr); suchen(); } });
  suchFeld.addEventListener("search", () => { clearTimeout(suchUhr); suchen(); });
  seite.append(
    h("div", { class: "seiten-kopf" }, h("h1", null, "Mail-Blatt"),
      h("div", { class: "werkzeuge" }, abrufKnopf, alleKnopf)),
    standEl,
    fortschrittEl,
    h("div", { class: "mail-werkzeug" }, suchFeld, h("div", { class: "chip-leiste", tid: "mail-filter" })),
    // D-236: Blättern steht unter der Liste, damit sie weiter oben beginnt
    h("div", { class: "mail-blatt" }, h("div", { class: "mail-listen-spalte" }, listeEl, blaetterEl), leseEl));
  seite.addEventListener("keydown", (ev) => {
    if (ev.altKey || ev.ctrlKey || ev.metaKey) return;
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    if (ev.target.closest("input, textarea, select, button, a")) return;
    ev.preventDefault();
    schritt(ev.key === "ArrowDown" ? 1 : -1);
  });
  await laden();
  abrufStandPruefen();
  return { titel: "Mail-Blatt" };

  function adresseSchreiben() {
    const q = {};
    if (postfach) q.postfach = postfach;
    if (filter !== "alle") q.filter = filter;
    if (suchtext) q.suche = suchtext;
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
      // am Handy zuerst die Liste: dort wird keine Mail vorgewählt (D-236)
      if (!gewaehlt && mails.length && !oberflaeche.istMobil()) gewaehlt = String(mails[0].id);
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
    if (suchtext) q.suche = suchtext;
    q.gruppieren = "ja";   // D-228: Mails derselben Zuordnung stehen beieinander
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
        h("thead", null, h("tr", null, ["Empfangen", "Absender und Betreff", "Zuordnung"].map((s) =>
          h("th", { scope: "col" }, s)))),
        h("tbody", null, mails.map(zeile)))
      : h("p", { class: "leer", tid: "mail-leer" }, leerText()));
    inhaltZeigen();
    adresseSchreiben();
  }

  function inhaltZeigen() {
    const mail = mails.find((m) => String(m.id) === gewaehlt);
    const mobil = oberflaeche.istMobil();
    leseEl.hidden = mobil && !mail;
    const zu = mobil && mail ? [h("button", { type: "button", class: "knopf-flach mail-lesen-zu", tid: "mail-lesen-schliessen",
      "aria-label": "Mail schließen", onclick: () => auswahlSetzen("", false) }, "✕")] : [];
    leseEl.replaceChildren(...zu, ...(mail ? lesen(mail, (ausloeser) => zuordnenDialog(mail, ausloeser, laden))
      : [h("p", { class: "leer" }, "Keine Mail ausgewählt.")]));
    if (mail && mail.ohne_inhalt) {
      const erneut = leseEl.querySelector("[data-testid=mail-inhalt-laden]");
      if (erneut) erneut.addEventListener("click", () => { delete mail.inhaltFehler; inhaltZeigen(); });
      else inhaltHolen(mail);
    }
  }

  /** D-243: Von der Mail sind nur Kopfzeilen gespiegelt; den Inhalt beim ersten Lesen aus dem Postfach holen. */
  async function inhaltHolen(mail) {
    if (mail.inhaltLaedt) return;
    mail.inhaltLaedt = true;
    try {
      const r = await api("POST", `/api/mail/nachrichten/${mail.id}/inhalt`, {});
      mail.text = r.text;
      delete mail.ohne_inhalt;
    } catch (e) {
      mail.inhaltFehler = e.message || "Der Inhalt konnte nicht geladen werden.";
    } finally {
      mail.inhaltLaedt = false;
    }
    if (String(mail.id) === gewaehlt) inhaltZeigen();
  }

  function auswahlSetzen(id, fokus) {
    gewaehlt = id === "" ? "" : String(id);
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
    if (gesamt === 0 && suchtext) return `Keine Mail enthält „${suchtext}“.`;
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

  function zeile(m, i) {
    const an = String(m.id) === gewaehlt;
    // D-228: Mails derselben Zuordnung stehen beieinander; die erste trägt die Zuordnung, die folgenden einen Verweis
    const inGruppe = m.gruppe !== null && m.gruppe !== undefined;
    const folge = inGruppe && i > 0 && mails[i - 1].gruppe === m.gruppe;
    const letzte = inGruppe && !(i + 1 < mails.length && mails[i + 1].gruppe === m.gruppe);
    const anzahl = inGruppe && !folge ? mails.filter((x) => x.gruppe === m.gruppe).length : 0;
    const tr = h("tr", { tid: `mail-${m.id}`, tabindex: an ? "0" : "-1", "aria-selected": an ? "true" : "false",
      class: "klickbar" + (an ? " gewaehlt" : ""), "data-zuordnung": art(m),
      "data-gruppe": inGruppe ? String(m.gruppe) : null,
      "data-gruppe-rolle": inGruppe ? (folge ? (letzte ? "ende" : "folge") : (letzte ? "allein" : "kopf")) : null },
    // Datum und Uhrzeit je in einer Zeile, ohne Umbruch mitten im Datum; Absender und Betreff untereinander
    h("td", { class: "mail-zeit", "data-zeitpunkt": m.empfangen || "", title: zeitText(m.empfangen) },
      h("div", null, tagText(m.empfangen)), h("div", { class: "klein" }, uhrText(m.empfangen))),
    h("td", { class: "mail-wer" },
      h("div", { class: "mail-absender", title: m.absender }, absenderName(m.absender)),
      h("div", { class: "mail-betreff" }, m.betreff || "(ohne Betreff)"),
      mehrerePostfaecher() ? h("div", { class: "klein mail-postfach" }, m.postfach) : null),
    h("td", { class: "mail-zuordnung-zelle" }, folge
      ? h("span", { class: "mail-gehoert-dazu", title: "Gehört zur selben Zuordnung wie die Mail darüber" }, "↳ gehört dazu")
      : [zuordnungKurz(m), anzahl > 1 ? h("div", { class: "klein mail-gruppe-anzahl", tid: "mail-gruppe-anzahl" }, `${anzahl} Mails zu dieser Zuordnung`) : null]));
    tr.addEventListener("click", () => auswahlSetzen(m.id, false));
    tr.addEventListener("keydown", (ev) => {
      if (ev.target !== tr || ev.key !== "Enter") return;
      ev.preventDefault();
      leseEl.focus({ preventScroll: true });
    });
    return tr;
  }

  function mehrerePostfaecher() {
    return !postfach && ((stand && stand.postfaecher) || []).length > 1;
  }

  function knoepfeSperren(an) {
    abrufKnopf.disabled = an;
    alleKnopf.disabled = an;
    abrufKnopf.textContent = an ? "Abruf läuft…" : "Mails abrufen";
  }

  /** D-246: läuft schon ein Abruf (Planer, anderer Tab), seinen Fortschritt zeigen. */
  async function abrufStandPruefen() {
    let st;
    try { st = await api("GET", "/api/mail/abruf/stand"); } catch (e) { return; }
    alleKnopf.hidden = !st.nur_koepfe;
    if (st.laeuft) abrufen(false, true);
  }

  async function alleAbrufen(ausloeser) {
    const ok = await bestaetigen("Die Kopfzeilen aller Mails im Postfach neu abrufen? Mails, die Kontor schon hat, "
      + "bleiben unverändert; ältere kommen mit Absender und Betreff dazu, Inhalte nur für Mails bekannter Anbieter. "
      + "Bei vielen Mails kann das einige Minuten dauern.", { titel: "Alle Kopfzeilen neu abrufen", ja: "Abrufen", ausloeser });
    if (ok) abrufen(true);
  }

  async function abrufen(alle, nurVerfolgen) {
    knoepfeSperren(true);
    abrufText = "";
    standEl.className = "mail-stand";
    standEl.textContent = "Mails werden abgerufen…";
    try {
      if (!nurVerfolgen) {
        try {
          await api("POST", "/api/mail/abruf" + abfrage({ hintergrund: "ja", ...(alle ? { alle_koepfe: "ja" } : {}) }), {});
        } catch (e) {
          if (e.code !== "mail_abruf_laeuft") throw e;   // läuft schon: diesem folgen
        }
      }
      const st = await verfolgen();
      if (st.fehler) throw new Error(st.fehler.meldung);
      abrufText = st.ergebnis ? abrufErgebnis(st.ergebnis) : "";
      seiteNr = 1;
      await laden();
    } catch (e) {
      standEl.textContent = e.message || "Der Abruf ist fehlgeschlagen.";
      standEl.className = "mail-stand fehler";
    } finally {
      knoepfeSperren(false);
      fortschrittEl.hidden = true;
    }
  }

  async function verfolgen() {
    for (;;) {
      const st = await api("GET", "/api/mail/abruf/stand");
      fortschrittZeigen(st);
      if (!st.laeuft) return st;
      await new Promise((r) => { setTimeout(r, 1000); });
    }
  }

  function fortschrittZeigen(st) {
    const zeilen = (st.postfaecher || []).map((p) => {
      const zahl = p.gesamt != null && ["koepfe", "inhalte", "speichern"].includes(p.schritt)
        ? ` ${tausend(p.erledigt || 0)} von ${tausend(p.gesamt)}` : "";
      const balken = p.gesamt ? h("progress", { max: String(p.gesamt), value: String(p.erledigt || 0) }) : null;
      return h("div", { class: "mail-fortschritt-zeile", tid: `mail-fortschritt-${p.postfach_id}`, "data-schritt": p.schritt },
        h("span", null, `${p.adresse}: ${SCHRITT[p.schritt] || p.schritt}${zahl}`), balken);
    });
    fortschrittEl.replaceChildren(st.alle_koepfe ? h("p", { class: "klein" }, "Alle Kopfzeilen werden neu abgerufen.") : "",
      ...zeilen);
    fortschrittEl.hidden = !st.laeuft || !zeilen.length;
  }
}

const SCHRITT = {
  wartet: "wartet", anmelden: "verbindet", nachrichten: "lädt Mails", koepfe: "Kopfzeilen",
  inhalte: "Inhalte bekannter Anbieter", speichern: "speichert", fertig: "fertig", fehlgeschlagen: "fehlgeschlagen",
  anmeldung_erforderlich: "Anmeldung nötig",
};

function abrufErgebnis(erg) {
  const kaesten = erg.postfaecher || [];
  if (!kaesten.length) return "Abruf beendet: kein aktives Postfach.";
  return "Abruf beendet: " + kaesten.map((p) => {
    if (p.status !== "erfolgreich") return `${p.adresse}: ${p.fehler && p.fehler.meldung ? p.fehler.meldung : p.status}`;
    const kopf = p.nachrichten_ohne_inhalt ? ` (${p.nachrichten_ohne_inhalt} nur mit Absender und Betreff)` : "";
    return `${p.adresse}: ${p.nachrichten_neu} neu${kopf}, ${p.nachrichten_vorhanden} schon da`;
  }).join("; ");
}

/** Zuordnung in der Liste (D-227): eine Zeile – Marke, Ziel, Betrag. Gründe und alle Buchungen stehen im Lesebereich. */
function zuordnungKurz(m) {
  const erwartungen = m.zuordnung;
  // jede Buchung nur einmal, auch wenn sie über Bestellnummer und erwartete Zahlung zugleich zugeordnet ist
  const buchungen = [];
  for (const b of [...haengt(m), ...erwartungen.flatMap((z) => z.buchungen)]) {
    if (!buchungen.some((x) => x.id === b.id)) buchungen.push(b);
  }
  const zeile = (zustand, marke, ziel, weitere, betrag, hinweis) => h("div", { class: "mail-zuordnung", "data-zustand": zustand, title: hinweis || null },
    h("span", { class: "mail-marke" }, marke),
    // D-236: der Betrag steht vor dem Namen und wird nie gekürzt – an ihm erkennt man die Buchung
    betrag === null || betrag === undefined ? h("span", { class: "mail-betrag" }) : betragEl("span", betrag, { class: "mail-betrag" }),
    h("span", { class: "mail-ziel" }, ziel),
    h("span", { class: "mail-weitere klein", tid: weitere ? "mail-weitere" : null }, weitere ? `+${weitere}` : ""));
  if (buchungen.length) {
    const weg = [haengt(m).some((b) => b.nummer) ? "Bestellnummer" : null, haengt(m).some((b) => !b.nummer) ? "von Hand" : null,
      erwartungen.some((z) => z.buchungen.length) ? "erwartete Zahlung" : null].filter(Boolean).join(", ");
    const erste = buchungen[0];
    const betrag = erste.betrag !== undefined && erste.betrag !== null ? erste.betrag : (erwartungen.find((z) => z.buchungen.some((b) => b.id === erste.id)) || {}).vorzeichen_betrag;
    return zeile("erfuellt", "Zugeordnet",
      buchungsKnopf(erste, true), buchungen.length - 1, betrag, `Zugeordnet über ${weg}${buchungen.length > 1 ? ` · ${buchungen.length} Buchungen` : ""}`);
  }
  if (erwartungen.length) {
    const z = erwartungen.find((x) => x.ueberfaellig) || erwartungen[0];
    return zeile(z.ueberfaellig ? "ueberfaellig" : z.zustand, z.ueberfaellig ? "Überfällig" : "Erwartet",
      z.haendler || GRUND[z.grund] || z.grund, erwartungen.length - 1, z.vorzeichen_betrag, "Erwartete Zahlung, noch keiner Buchung zugeordnet");
  }
  return h("span", { class: "mail-ohne" }, "–");
}

function buchungsKnopf(b, kurz) {
  const name = b.empfaenger || b.konto || "Buchung";
  const datum = datumText(b.datum);
  return h("button", { type: "button", class: "knopf-link", tid: `mail-buchung-${b.id}`, title: `${datum} ${name}`,
    onclick: (ev) => { ev.stopPropagation(); oberflaeche.zurBuchung(b.konto_id, b.id); } },
  `${kurz ? datum.slice(0, 6) : datum} ${name}`);
}

const zwei = (n) => String(n).padStart(2, "0");
/** „Heute“, „Gestern“ oder das Datum; die Uhrzeit steht in der Zeile darunter. */
function tagText(wert) {
  const d = new Date(wert);
  if (!wert || Number.isNaN(d.getTime())) return wert || "";
  const tag = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const abstand = Math.round((tag(new Date()) - tag(d)) / 86400000);
  if (abstand === 0) return "Heute";
  if (abstand === 1) return "Gestern";
  return `${zwei(d.getDate())}.${zwei(d.getMonth() + 1)}.${d.getFullYear()}`;
}
function uhrText(wert) {
  const d = new Date(wert);
  return !wert || Number.isNaN(d.getTime()) ? "" : `${zwei(d.getHours())}:${zwei(d.getMinutes())}`;
}
/** Anzeigename des Absenders („Name <adresse>“ → Name); die volle Angabe steht im Tooltip und im Lesebereich. */
function absenderName(absender) {
  const m = /^\s*"?([^"<]*?)"?\s*<[^>]*>\s*$/.exec(absender || "");
  return (m && m[1].trim()) || absender || "(ohne Absender)";
}

/** Beträge im Betreff und Text einer Mail („12,34 €“, „EUR 1.234,56“) in Cent. */
function betraegeDerMail(m) {
  const aus = new Set();
  const text = `${m.betreff || ""} ${m.text || ""}`;
  for (const t of text.matchAll(/(?:€|EUR)\s*(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})(?!\d)|(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})\s*(?:€|EUR)/g)) {
    const ganz = (t[1] || t[3]).replace(/\./g, "");
    aus.add(Number(ganz) * 100 + Number(t[2] || t[4]));
  }
  return aus;
}

const tageVersetzt = (iso, tage) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + tage);
  return `${d.getFullYear()}-${zwei(d.getMonth() + 1)}-${zwei(d.getDate())}`;
};

/** D-226: Mail von Hand an eine Buchung hängen. Vorschläge: Buchungen um das Maildatum, passende Beträge zuerst. */
function zuordnenDialog(m, ausloeser, danach) {
  const d0 = new Date(m.empfangen);
  const mailTag = Number.isNaN(d0.getTime()) ? new Date().toISOString().slice(0, 10)
    : `${d0.getFullYear()}-${zwei(d0.getMonth() + 1)}-${zwei(d0.getDate())}`;
  const betraege = betraegeDerMail(m);
  dialog("mail-zuordnen-dialog", "Mail einer Buchung zuordnen", (inhalt, d) => {
    const von = h("input", { type: "date", value: tageVersetzt(mailTag, -14), tid: "mail-zuordnen-von" });
    const bis = h("input", { type: "date", value: tageVersetzt(mailTag, 30), tid: "mail-zuordnen-bis" });
    const text = h("input", { type: "search", placeholder: "Empfänger, Verwendungszweck, Betrag …", tid: "mail-zuordnen-suche" });
    const liste = h("div", { class: "mail-zuordnen-liste", tid: "mail-zuordnen-liste", role: "listbox", "aria-label": "Buchungen" });
    const ok = knopf("Zuordnen", { class: "knopf knopf-haupt", tid: "mail-zuordnen-ok", disabled: true });
    let buchungen = [];
    let wahl = null;
    let nr = 0;
    const betragVon = (b) => b.splits.filter((s) => BESTAND.has((kontoNach(s.konto_id) || {}).art)).reduce((n, s) => n + s.betrag, 0);
    const zeichnen = () => {
      const woerter = text.value.toLowerCase().split(/\s+/).filter(Boolean);
      const passt = (b) => {
        const heu = `${b.empfaenger ? b.empfaenger.name : ""} ${b.verwendungszweck || ""} ${(Math.abs(betragVon(b)) / 100).toFixed(2).replace(".", ",")}`.toLowerCase();
        return woerter.every((w) => heu.includes(w));
      };
      const sicht = buchungen.filter(passt)
        .sort((a, b) => Number(betraege.has(Math.abs(betragVon(b)))) - Number(betraege.has(Math.abs(betragVon(a)))));
      if (!sicht.some((b) => b.id === wahl)) wahl = null;
      ok.disabled = wahl === null;
      liste.replaceChildren(...(sicht.length ? sicht.map((b) => {
        const treffer = betraege.has(Math.abs(betragVon(b)));
        const el = h("div", { class: "mail-zuordnen-zeile" + (b.id === wahl ? " gewaehlt" : ""), role: "option", tabindex: "0",
          tid: `mail-zuordnen-buchung-${b.id}`, "aria-selected": b.id === wahl ? "true" : "false", "data-betrag-passt": treffer ? "ja" : "nein" },
        h("span", { class: "mail-zuordnen-datum" }, datumText(b.datum)),
        h("span", { class: "mail-zuordnen-text" }, h("strong", null, b.empfaenger ? nameAnzeige(b.empfaenger.name) : "ohne Empfänger"),
          b.verwendungszweck ? ` · ${b.verwendungszweck}` : ""),
        treffer ? h("span", { class: "grund-marke" }, "Betrag passt") : null,
        betragEl("span", betragVon(b), { class: "zahl" }));
        const waehlen = () => { wahl = b.id; zeichnen(); };
        el.addEventListener("click", waehlen);
        el.addEventListener("dblclick", () => { wahl = b.id; ok.disabled = false; ok.click(); });
        el.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); waehlen(); } });
        return el;
      }) : [h("p", { class: "leer" }, buchungen.length ? "Keine Buchung passt zur Suche." : "Keine Buchungen in diesem Zeitraum.")]));
    };
    const holen = async () => {
      const lauf = ++nr;
      liste.replaceChildren(h("p", { class: "leer" }, "Buchungen werden geladen…"));
      try {
        const r = await api("GET", `/api/buchungen${abfrage({ von: von.value, bis: bis.value, sortierung: "-datum", pro_seite: 500 })}`);
        if (lauf !== nr) return;
        buchungen = r.eintraege;
        zeichnen();
      } catch (e) {
        if (lauf === nr) liste.replaceChildren(h("p", { class: "fehler", role: "alert" }, e.message));
      }
    };
    von.addEventListener("change", holen);
    bis.addEventListener("change", holen);
    text.addEventListener("input", zeichnen);
    ok.addEventListener("click", () => imDialog(d, ok, async () => {
      await aktion(() => api("POST", `/api/mail/nachrichten/${m.id}/buchung`, { buchung_id: wahl }),
        { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Mail an die Buchung gehängt." });
      if (danach) danach();
    }));
    inhalt.append(
      h("p", { class: "klein" }, `„${m.betreff || "(ohne Betreff)"}“ von ${absenderName(m.absender)}, ${zeitText(m.empfangen)}. `
        + "Die Mail wird als Dokument an die gewählte Buchung gehängt."),
      h("div", { class: "formular-zeile" }, feld("Buchungen von", von), feld("bis", bis), feld("Suchen", text)),
      liste, knopfLeiste(ok, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
    holen();
  }, { ausloeser, klasse: "dialog-breit" });
}

function lesen(m, zuordnen) {
  return [
    h("h2", null, m.betreff || "(ohne Betreff)"),
    h("dl", { class: "mail-kopf" },
      h("dt", null, "Von"), h("dd", null, m.absender),
      h("dt", null, "Postfach"), h("dd", null, m.postfach),
      h("dt", null, "Empfangen"), h("dd", null, zeitEl("span", m.empfangen)),
      h("dt", null, "Stand"), h("dd", null, standDerMail(m))),
    h("h3", null, "Zuordnung"),
    h("div", null, zuordnungAusfuehrlich(m)),
    zuordnen ? h("p", null, knopf("Buchung zuordnen…", { tid: "mail-zuordnen", onclick: (ev) => zuordnen(ev.currentTarget) })) : null,
    h("h3", null, "Text"),
    m.ohne_inhalt ? textOhneInhalt(m) : h("pre", { class: "mail-text", tid: "mail-text" }, m.text || ""),
  ];
}

function textOhneInhalt(m) {
  if (m.inhaltFehler) {
    return h("div", { class: "mail-text", tid: "mail-text", "data-inhalt": "fehler" },
      h("p", { role: "alert" }, m.inhaltFehler), knopf("Erneut laden", { tid: "mail-inhalt-laden" }));
  }
  return h("p", { class: "mail-text klein", tid: "mail-text", "data-inhalt": "laedt", role: "status" },
    "Von dieser Mail sind nur Absender und Betreff gespeichert. Der Inhalt wird aus dem Postfach geladen …");
}

function standDerMail(m) {
  const a = art(m);
  if (a === "keine") return "Nicht zugeordnet. Keine Buchung trägt eine Bestellnummer aus dieser Mail.";
  if (haengt(m).length) return haengt(m).some((b) => b.nummer) ? "Über die Bestellnummer an eine Buchung gehängt." : "Von Hand an eine Buchung gehängt.";
  if (a === "erwartet") return "Erwartet. Eine Zahlung ist vorgemerkt, aber noch keiner Buchung zugeordnet.";
  return "Einer Buchung zugeordnet.";
}

function angehaengtAusfuehrlich(m) {
  return h("ul", { class: "mail-zuordnung-liste", tid: "mail-angehaengt" }, haengt(m).map((b) => h("li", {
    tid: `mail-angehaengt-${b.id}`, "data-zustand": "erfuellt",
  },
  buchungsKnopf(b),
  h("p", { class: "mail-warum" }, b.warum),
  b.verwendungszweck ? h("span", { class: "klein" }, b.verwendungszweck) : null)));
}

function zuordnungAusfuehrlich(m) {
  if (haengt(m).length) return [angehaengtAusfuehrlich(m), m.zuordnung.length ? erwartungenAusfuehrlich(m) : null];
  if (!m.zuordnung.length) {
    return h("p", { tid: "mail-ohne-zuordnung" }, "Diese Mail ist keiner Buchung zugeordnet.");
  }
  return erwartungenAusfuehrlich(m);
}

function erwartungenAusfuehrlich(m) {
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
