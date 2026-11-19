/* Kontor – Abschnitt „Bankzugang (FinTS)“ der Einstellungen (D-199): Server-Adresse, Bankleitzahl, Benutzerkennung,
 * Kunden-ID, Produkt-ID, TAN-Verfahren und die Auswahl der Konten. Die PIN wird hier nur an den Arbeitsspeicher des
 * Servers übergeben (PUT /api/sync/pin) und nie gespeichert. Betriebszustand: kein Eintrag im Änderungsprotokoll.
 * Gliederung in vier Schritte (D-207); Kunden-ID, Produkt-ID und das Diagnoseprotokoll stehen unter „Erweitert“. */
import { api, h, oberflaeche } from "./kern.js";
import { feld, knopf } from "./ui.js";
import { erweitert } from "./einstellungen.js";

const FELDER = [
  ["url", "FinTS-Server-Adresse", "url", "https-Adresse des FinTS-Servers der Bank"],
  ["blz", "Bankleitzahl", "text", "8 Ziffern"],
  ["benutzer", "Zugangsnummer / Benutzerkennung", "text", ""],
  ["kunden_id", "Kunden-ID (falls abweichend)", "text", "leer = wie Benutzerkennung", true],
  ["produkt_id", "FinTS-Produkt-ID", "text", "Registrierungsnummer der Deutschen Kreditwirtschaft", true],
];

const gruppe = (schluessel, titel, ...inhalt) => h("div", { class: "einst-gruppe", "data-einstellung": schluessel }, h("h4", null, titel), inhalt);

/** z: Antwort von GET /api/bank/zugang; pin: {vorhanden, gesetzt(), status, verwerfen} aus den Einstellungen. */
export async function bankzugangAbschnitt(z, pin) {
  const pinVorhanden = pin.vorhanden;
  const karte = h("section", { class: "karte", tid: "bankzugang", "data-aenderbar": z.aenderbar ? "ja" : "nein",
    "data-vollstaendig": z.vollstaendig ? "ja" : "nein" }, h("h3", null, "Bankzugang (FinTS)"));
  if (!z.aenderbar) {
    karte.append(h("p", { tid: "bankzugang-hinweis" }, z.plugin === "mock"
      ? "Im Mock-Modus gibt es keinen echten Bankzugang." : "Der Bankzugang ist nur mit dem FinTS-Plugin einstellbar."));
    return karte;
  }
  const meldung = h("p", { tid: "bankzugang-meldung", role: "status", "aria-live": "polite", hidden: true });
  // Die Meldung erscheint in dem Schritt, in dem zuletzt etwas ausgelöst wurde.
  const hier = (el) => { const g = el && el.closest(".einst-gruppe, .einst-erweitert"); if (g) g.append(meldung); };
  const sagen = (text, fehler) => {
    meldung.hidden = !text;
    meldung.textContent = text || "";
    meldung.dataset.art = fehler ? "fehler" : "hinweis";
  };
  const eingaben = {};
  const felder = { vorn: [], erweitert: [] };
  for (const [name, titel, typ, hinweis, selten] of FELDER) {
    eingaben[name] = h("input", { type: typ, tid: `bankzugang-${name}`, autocomplete: "off", spellcheck: "false", value: z[name] || "" });
    felder[selten ? "erweitert" : "vorn"].push(feld(titel, eingaben[name], hinweis));
  }
  // die Produkt-ID ist Pflicht: fehlt sie, ist „Erweitert“ von Anfang an offen
  const kennungen = erweitert("bank-kennungen", "Kunden-ID, Produkt-ID", h("div", { "data-einstellung": "kennungen" }, felder.erweitert), !z.produkt_id);
  const verfahren = h("select", { tid: "bankzugang-tan-verfahren" });
  const verfahrenFuellen = (liste, gewaehlt) => {
    verfahren.replaceChildren(h("option", { value: "" }, "automatisch (erstes unterstütztes Verfahren)"),
      ...liste.map((v) => h("option", { value: v.code }, `${v.name} (${v.code})`)));
    if (gewaehlt && !liste.some((v) => v.code === gewaehlt)) verfahren.append(h("option", { value: gewaehlt }, `Verfahren ${gewaehlt}`));
    verfahren.value = gewaehlt || "";
  };
  verfahrenFuellen([], z.tan_verfahren);

  const werte = () => ({ ...Object.fromEntries(FELDER.map(([n]) => [n, eingaben[n].value.trim() || null])),
    tan_verfahren: verfahren.value || null });
  let stand = JSON.stringify(werte());
  const speichern = async () => {
    const w = werte();
    if (JSON.stringify(w) === stand) return true;
    try {
      await api("PUT", "/api/bank/zugang", w);
      stand = JSON.stringify(w);
      return true;
    } catch (e) {
      const d = Array.isArray(e.details) ? e.details.map((x) => `${x.ort[x.ort.length - 1]}: ${x.meldung}`).join(" ") : "";
      if (Array.isArray(e.details) && e.details.some((x) => ["kunden_id", "produkt_id"].includes(x.ort[x.ort.length - 1]))) kennungen.open = true;
      sagen(d || e.message, true);
      return false;
    }
  };
  // Aktionen mit Bankverbindung speichern zuerst, damit die Bank genau die angezeigten Angaben bekommt.
  const mitBank = (k, f) => async () => {
    hier(k);
    sagen("");
    k.disabled = true;
    try { if (await speichern()) await f(); } catch (e) { sagen(e.message, true); } finally { k.disabled = false; }
  };

  // PIN: nur Arbeitsspeicher
  const pinFeld = h("input", { type: "password", tid: "bankzugang-pin", autocomplete: "off", maxlength: "64", spellcheck: "false" });
  const pinStatus = h("small", { class: "hinweis", tid: "bankzugang-pin-status", "data-vorhanden": pinVorhanden ? "ja" : "nein" },
    "Für Abrufe bei der Bank wird die PIN gebraucht. Sie wird nie gespeichert und liegt nur im Arbeitsspeicher des Servers.");
  const pinKnopf = knopf("PIN übergeben", { tid: "bankzugang-pin-senden", onclick: async (e) => {
    hier(e.currentTarget);
    const w = pinFeld.value;
    pinFeld.value = "";
    if (!w) { sagen("Bitte die PIN eingeben.", true); return; }
    try {
      await api("PUT", "/api/sync/pin", { pin: w });
      pinStatus.dataset.vorhanden = "ja";
      pin.gesetzt();
      sagen("PIN übergeben.");
    } catch (f) { sagen(f.message, true); }
  } });

  // Konten
  const kontenBereich = h("div", { tid: "bankzugang-konten" });
  const kontenZeigen = (konten) => {
    kontenBereich.replaceChildren();
    if (!konten.length) {
      kontenBereich.append(h("p", { class: "leer" }, "Noch keine Konten abgerufen. Ohne Auswahl werden bei der Synchronisation alle Konten der Bank abgefragt."));
      return;
    }
    const haken = konten.map((k) => {
      const c = h("input", { type: "checkbox", tid: "bankzugang-konto", "data-iban": k.iban });
      c.checked = !!k.aktiv;
      return [k, c];
    });
    kontenBereich.append(h("ul", { class: "auswahlliste" }, haken.map(([k, c]) => h("li", null, h("label", null, c,
      ` ${k.name || "Konto"} · ${k.iban}${k.bic ? ` · ${k.bic}` : ""}${k.inhaber ? ` · ${k.inhaber}` : ""}`)))),
    knopf("Kontenauswahl speichern", { tid: "bankzugang-konten-speichern", onclick: async (e) => {
      hier(e.currentTarget);
      try {
        await api("PUT", "/api/bank/zugang/konten", { ibans: haken.filter(([, c]) => c.checked).map(([k]) => k.iban) });
        sagen("Kontenauswahl gespeichert.");
      } catch (f) { sagen(f.message, true); }
    } }));
  };
  kontenZeigen(z.konten);

  // TAN zum Kontenabruf (starke Kundenauthentifizierung beim Dialogbeginn)
  const tanBereich = h("div", { tid: "bankzugang-tan", class: "karte", hidden: true });
  const tanZeigen = (t) => {
    const eingabe = h("input", { type: "text", tid: "bankzugang-tan-eingabe", inputmode: "numeric", autocomplete: "one-time-code", maxlength: "64" });
    const senden = knopf("TAN senden", { tid: "bankzugang-tan-senden", class: "knopf knopf-haupt" });
    senden.addEventListener("click", async () => {
      const w = eingabe.value.trim();
      eingabe.value = "";
      if (!w) { sagen("Bitte die TAN eingeben.", true); return; }
      senden.disabled = true;
      try {
        abrufErgebnis(await api("POST", "/api/bank/zugang/konten/abrufen", { vorgang: t.vorgang, tan: w }));
      } catch (e) {
        sagen(e.message, true);
        if (e.code !== "tan_ungueltig") tanBereich.hidden = true;
      } finally { senden.disabled = false; }
    });
    tanBereich.replaceChildren(h("p", { tid: "bankzugang-tan-challenge" }, t.challenge),
      t.bild ? h("img", { tid: "bankzugang-tan-bild", class: "tan-bild", alt: "Grafik der TAN-Anforderung", src: t.bild }) : null,
      feld("TAN", eingabe), senden);
    tanBereich.hidden = false;
    eingabe.focus();
  };
  const abrufErgebnis = (r) => {
    if (r.tan_erforderlich) { tanZeigen(r.tan_erforderlich); sagen("Die Bank verlangt eine TAN."); return; }
    tanBereich.hidden = true;
    tanBereich.replaceChildren();
    kontenZeigen(r.konten);
    sagen(r.konten.length ? `${r.konten.length} Konten abgerufen.` : "Die Bank hat keine abrufbaren Konten gemeldet.", !r.konten.length);
  };

  const speicherKnopf = knopf("Bankzugang speichern", { tid: "bankzugang-speichern", class: "knopf knopf-haupt" });
  speicherKnopf.addEventListener("click", mitBank(speicherKnopf, async () => { sagen("Bankzugang gespeichert."); await oberflaeche.neuLaden(); }));
  const verfahrenKnopf = knopf("TAN-Verfahren abrufen", { tid: "bankzugang-verfahren-abrufen" });
  verfahrenKnopf.addEventListener("click", mitBank(verfahrenKnopf, async () => {
    const r = await api("POST", "/api/bank/zugang/tan-verfahren");
    verfahrenFuellen(r.verfahren, verfahren.value || z.tan_verfahren);
    sagen(`${r.verfahren.length} TAN-Verfahren abgerufen. Auswahl mit „Bankzugang speichern“ übernehmen.`);
  }));
  const kontenKnopf = knopf("Konten abrufen", { tid: "bankzugang-konten-abrufen" });
  kontenKnopf.addEventListener("click", mitBank(kontenKnopf, async () => abrufErgebnis(await api("POST", "/api/bank/zugang/konten/abrufen"))));
  const leiste = (...k) => h("div", { class: "knopf-leiste" }, k);
  const diagnose = await diagnoseBereich(sagen, hier);
  karte.append(
    h("p", { class: "klein" }, "Einrichten in dieser Reihenfolge. Aktionen mit Bankverbindung speichern die Zugangsdaten vorher von selbst."),
    gruppe("zugang", "1 · Zugangsdaten", felder.vorn, kennungen, leiste(speicherKnopf), meldung),
    gruppe("pin", "2 · Bank-PIN", pin.status, feld("Bank-PIN", pinFeld), pinStatus, leiste(pinKnopf, pin.verwerfen)),
    gruppe("tan", "3 · TAN-Verfahren", feld("TAN-Verfahren", verfahren, "Die Liste kommt von der Bank: „TAN-Verfahren abrufen“."), leiste(verfahrenKnopf)),
    gruppe("konten", "4 · Konten", kontenBereich, leiste(kontenKnopf), tanBereich),
    erweitert("bank-diagnose", "Diagnoseprotokoll", diagnose.el, diagnose.aktiv));
  if (z.gespeichert.length === 0 && z.vollstaendig) {
    karte.append(h("p", { class: "klein" }, "Die Angaben stammen aus der Konfiguration des Dienstes (KONTOR_FINTS_…) und gelten, bis hier etwas gespeichert wird."));
  }
  return karte;
}

/* D-203: Diagnoseprotokoll des Austauschs mit der Bank – nur Strukturangaben, keine persönlichen Daten. */
async function diagnoseBereich(sagen, hier) {
  const d = await api("GET", "/api/bank/zugang/diagnose");
  const haken = h("input", { type: "checkbox", tid: "bankzugang-diagnose-aktiv" });
  haken.checked = d.aktiv;
  const ausgabe = h("pre", { tid: "bankzugang-diagnose-zeilen", class: "diagnose", tabindex: "0" });
  const zeigen = (r) => {
    ausgabe.textContent = r.zeilen.length ? r.zeilen.join("\n") : (r.aktiv
      ? "Noch keine Einträge. Jetzt z. B. „Konten abrufen“ oder eine Synchronisation starten."
      : "Das Diagnoseprotokoll ist ausgeschaltet.");
    ausgabe.dataset.zeilen = String(r.zeilen.length);
  };
  zeigen(d);
  haken.addEventListener("change", async () => {
    hier(haken);
    try { zeigen(await api("PUT", "/api/bank/zugang/diagnose", { aktiv: haken.checked })); } catch (e) { haken.checked = !haken.checked; sagen(e.message, true); }
  });
  const laden = knopf("Protokoll aktualisieren", { tid: "bankzugang-diagnose-laden", onclick: async () => {
    try { zeigen(await api("GET", "/api/bank/zugang/diagnose")); } catch (e) { sagen(e.message, true); }
  } });
  const kopieren = knopf("In die Zwischenablage", { tid: "bankzugang-diagnose-kopieren", onclick: async () => {
    try { await navigator.clipboard.writeText(ausgabe.textContent); sagen("Protokoll kopiert."); } catch { sagen("Kopieren nicht möglich; bitte den Text markieren.", true); }
  } });
  return { aktiv: d.aktiv, el: h("div", { tid: "bankzugang-diagnose", "data-einstellung": "diagnose" },
    h("label", null, haken, " Diagnoseprotokoll führen (was mit der Bank ausgetauscht wird)"),
    h("p", { class: "klein" }, "Das Protokoll enthält Segmente, Rückmeldecodes, Formate und Entscheidungen des Abrufs – nie PIN, TAN, Zugangskennung, IBAN, Kontonummer, Namen, Beträge oder Umsätze. Es liegt nur im Arbeitsspeicher und zusätzlich im Log des Dienstes."),
    h("div", { class: "knopf-leiste" }, laden, kopieren), ausgabe) };
}
