/* Kontor – Einstellungen (oberflaeche.md 13.2; Feature „einstellungen“, D-207).
 *
 * Statt einer langen Seite: wenige Bereiche mit einer Navigation (Desktop: Spalte links, Handy: Liste, die in den
 * Bereich führt), darüber eine Suche, die zur einzelnen Einstellung springt. Jeder Eintrag der Navigation nennt den
 * Stand des Bereichs. Seltenes steht je Bereich unter „Erweitert“ (eingeklappt).
 *
 * Alle Bereiche werden einmal aufgebaut; gezeigt wird genau einer (`hidden` an den übrigen). Der gewählte Bereich
 * steht im Abfrageteil (`/einstellungen?bereich=bank`), damit die Einstellungen ein einziger Tab bleiben. */
import { abfrage, aktion, anmeldung, api, erfolgsmeldung, h, melde, nachName, oberflaeche, passt, stamm, tid, zeitText } from "./kern.js";
import { bestaetigen, dialog, feld, imDialog, knopf, knopfLeiste } from "./ui.js";
import { layoutZuruecksetzen } from "./konto.js";
import { bankzugangAbschnitt } from "./bankzugang.js";

export const BEREICHE = [
  ["allgemein", "Allgemein"],
  ["bank", "Bank"],
  ["mail", "Mail"],
  ["benachrichtigungen", "Benachrichtigungen"],
  ["sicherheit", "Sicherheit"],
  ["daten", "Daten und Sicherung"],
];
const TITEL = Object.fromEntries(BEREICHE);

/* Suchverzeichnis: [Bereich, Schlüssel, Titel, weitere Suchwörter]. Der Schlüssel steht als `data-einstellung` am
 * Element der Einstellung; Einträge ohne Element (z. B. Bankzugang im Mock-Modus) erscheinen nicht in der Suche. */
const VERZEICHNIS = [
  ["allgemein", "design", "Design (hell, dunkel)", "thema farbe farben dark mode dunkelmodus nachtmodus aussehen darstellung"],
  ["allgemein", "erfolgsmeldung", "Meldung mit „Rückgängig“ nach Änderungen", "erfolgsmeldung rückgängig anzeige hinweis toast benachrichtigung einblendung undo"],
  ["allgemein", "layout", "Layout zurücksetzen", "spalten breite ansicht panels darstellung"],
  ["allgemein", "betrieb", "Betriebsmodus und Version", "mock echtbetrieb szenario instanz"],
  ["bank", "zugang", "Bankzugang (FinTS)", "hbci server url adresse bankleitzahl blz zugangsnummer benutzerkennung login zugangsdaten"],
  ["bank", "pin", "Bank-PIN", "passwort geheimzahl uebergeben verwerfen arbeitsspeicher"],
  ["bank", "tan", "TAN-Verfahren", "pushtan phototan chiptan smstan freigabe"],
  ["bank", "konten", "Konten der Bank auswählen", "iban konto abrufen kontenauswahl synchronisation"],
  ["bank", "kennungen", "Kunden-ID und Produkt-ID", "kundennummer registrierungsnummer fints produktid kundenid"],
  ["bank", "diagnose", "Diagnoseprotokoll der Bankverbindung", "log fehlersuche debug protokoll fints"],
  ["mail", "postfaecher", "Mail-Postfächer", "postfach gmail imap email e-mail adresse app-passwort anlegen"],
  ["mail", "abruf", "Mails jetzt abrufen", "abrufen abgleich postfach"],
  ["mail", "oauth", "OAuth-Client-Secret", "google oauth2 client secret geheimnis"],
  ["benachrichtigungen", "zustellung", "Zustellung und Test-Benachrichtigung", "ntfy push testen senden handy"],
  ["benachrichtigungen", "ntfy", "ntfy-Token", "token zugang geheimnis push"],
  ["sicherheit", "passwort", "Passwort ändern", "login kennwort anmeldung"],
  ["sicherheit", "abmelden", "Abmelden", "logout ausloggen sitzung"],
  ["sicherheit", "schutz", "Schutz der Geheimnisse", "verschluesselung sperren entsperren gemerkte pin login-passwort"],
  ["daten", "sicherungspunkte", "Sicherungspunkte (stündlich, zurück und vorwärts)", "backup wiederherstellen rollback restore stündlich zeitpunkt"],
  ["daten", "sicherung", "Sicherung herunterladen", "backup datensicherung export download"],
  ["daten", "einspielen", "Sicherung einspielen", "backup wiederherstellen restore zuruecksichern datensicherung"],
  ["daten", "tags", "Tags", "schlagwort label umbenennen loeschen"],
];

const abschnitt = (titel, ...inhalt) => h("section", { class: "karte" }, h("h3", null, titel), inhalt);
const leer = (text) => h("p", { class: "leer" }, text);
const istMobil = () => (tid("app") || {}).dataset?.layout === "mobil";

/* „Erweitert“: eingeklappter Bereich für Seltenes. Was der Mensch aufgeklappt hat, bleibt über das Neuladen der
 * Seite nach einer Aktion hinweg offen (nur im Arbeitsspeicher dieses Fensters). */
const aufgeklappt = new Set();
export function erweitert(schluessel, inhaltsangabe, inhalt, offen) {
  const d = h("details", { class: "einst-erweitert", tid: `einstellungen-erweitert-${schluessel}` },
    h("summary", null, h("span", { class: "einst-erweitert-titel" }, "Erweitert"), ` ${inhaltsangabe}`), inhalt);
  d.open = !!offen || aufgeklappt.has(schluessel);
  d.addEventListener("toggle", () => { if (d.open) aufgeklappt.add(schluessel); else aufgeklappt.delete(schluessel); });
  return d;
}

export async function einstellungen(seite, _p, suche, kontext) {
  const still = (versprechen) => versprechen.catch(() => null);
  const [status, sync, geheim, zust, postfaecher, zugang, schutz] = await Promise.all([api("GET", "/api/status"),
    api("GET", "/api/sync/status"), api("GET", "/api/geheimnisse"), api("GET", "/api/benachrichtigungen/zustellung"),
    api("GET", "/api/mail/postfaecher"), api("GET", "/api/bank/zugang"), still(api("GET", "/api/geheimnisse/schutz"))]);
  seite.append(h("div", { class: "seiten-kopf" }, h("h1", null, "Einstellungen")));

  // ---------------------------------------------------------------- Stand je Bereich (Navigation)
  const standEl = {};
  const stand = (bereich, text, zustand) => {
    standEl[bereich].textContent = text;
    standEl[bereich].dataset.zustand = zustand || "neutral";
  };
  const THEMA_TEXT = { system: "wie System", hell: "Hell", dunkel: "Dunkel" };
  const pin = { vorhanden: !!sync.pin_vorhanden };
  const bankStand = () => {
    if (!zugang.aenderbar) return stand("bank", zugang.plugin === "mock" ? "Mock-Modus, kein echter Bankzugang" : "Nicht einstellbar");
    if (!zugang.vollstaendig) return stand("bank", "Bankzugang unvollständig", "offen");
    const aktiv = zugang.konten.filter((k) => k.aktiv).length;
    const konten = zugang.konten.length ? `${aktiv} von ${zugang.konten.length} Konten ausgewählt` : "alle Konten der Bank";
    return stand("bank", `Zugang vollständig · ${konten} · PIN ${pin.vorhanden ? "vorhanden" : "fehlt"}`, pin.vorhanden ? "ok" : "offen");
  };
  const staende = () => {
    stand("allgemein", `Design: ${THEMA_TEXT[kontext.thema.lesen()] || "wie System"}`);
    bankStand();
    stand("mail", postfaecher.length === 0 ? "Kein Postfach eingerichtet" : postfaecher.length === 1 ? "1 Postfach" : `${postfaecher.length} Postfächer`,
      postfaecher.length ? "ok" : "neutral");
    if (zust.plugin === "keins") stand("benachrichtigungen", "Zustellung aus");
    else if (zust.aufgegeben || zust.letzter_fehler) stand("benachrichtigungen", `Zustellung über ${zust.plugin} · zuletzt fehlgeschlagen`, "fehler");
    else stand("benachrichtigungen", `Zustellung über ${zust.plugin}` + (zust.ausstehend ? ` · ${zust.ausstehend} ausstehend` : ""), "ok");
    const schutzText = !schutz ? "" : !schutz.aktiv ? " · Geheimnisschutz aus" : schutz.gesperrt ? " · Geheimnisse gesperrt" : " · Geheimnisschutz ein";
    stand("sicherheit", (anmeldung.aktiv ? "Anmeldung aktiv" : "Ohne Anmeldung") + schutzText,
      schutz && schutz.aktiv && schutz.gesperrt ? "offen" : schutz && schutz.aktiv ? "ok" : "neutral");
    stand("daten", `Sicherung · ${stamm.tags.length === 1 ? "1 Tag" : `${stamm.tags.length} Tags`}`);
  };

  // ---------------------------------------------------------------- Bereiche
  const bereiche = {
    allgemein: allgemein(status, kontext, staende),
    bank: await bank(zugang, sync, pin, bankStand),
    mail: mail(postfaecher, geheim),
    benachrichtigungen: benachrichtigungen(zust, geheim),
    sicherheit: sicherheit(schutz, kontext),
    daten: daten(),
  };

  // ---------------------------------------------------------------- Gerüst: Suche, Navigation, Inhalt
  const sucheFeld = h("input", { type: "search", tid: "einstellungen-suche", autocomplete: "off", spellcheck: "false",
    placeholder: "z. B. PIN, Sicherung, Design", "aria-controls": "einstellungen-treffer" });
  const treffer = h("ul", { class: "einst-treffer", tid: "einstellungen-treffer", id: "einstellungen-treffer", "aria-label": "Gefundene Einstellungen", hidden: true });
  const trefferStand = h("p", { class: "klein", tid: "einstellungen-treffer-stand", role: "status", "aria-live": "polite", hidden: true });
  const navLinks = {};
  const navListe = h("ul", null, BEREICHE.map(([name, titel]) => {
    standEl[name] = h("span", { class: "einst-status", tid: `einstellungen-status-${name}` });
    navLinks[name] = h("a", { href: `/einstellungen?bereich=${name}`, tid: `einstellungen-nav-${name}`, "data-bereich": name },
      h("span", { class: "einst-nav-titel" }, titel), standEl[name]);
    return h("li", null, navLinks[name]);
  }));
  const nav = h("nav", { class: "einst-nav", tid: "einstellungen-nav", "aria-label": "Bereiche der Einstellungen" }, navListe);
  const bereichTitel = h("h2", { tid: "einstellungen-bereich-titel", tabindex: "-1" });
  const zurueck = h("a", { href: "/einstellungen", class: "einst-zurueck", tid: "einstellungen-zurueck" }, "‹ Alle Einstellungen");
  const felder = {};
  const inhalt = h("div", { class: "einst-inhalt" }, zurueck, bereichTitel, BEREICHE.map(([name]) => {
    felder[name] = h("div", { class: "einst-bereich", tid: `einstellungen-bereich-${name}`, "data-bereich": name, hidden: true }, bereiche[name]);
    return felder[name];
  }));
  const wurzel = h("div", { class: "einst", tid: "einstellungen" },
    h("div", { class: "einst-seite" }, h("div", { class: "einst-suche", role: "search" }, feld("Einstellung suchen", sucheFeld), trefferStand, treffer), nav),
    inhalt);
  seite.append(wurzel);
  staende();

  /** Bereich zeigen. `name` null: kein Bereich gewählt (Desktop zeigt dann „Allgemein“, das Handy nur die Liste). */
  const zeigen = (name, o) => {
    const opt = o || {};
    const sichtbar = name || BEREICHE[0][0];
    wurzel.dataset.gewaehlt = name ? "ja" : "nein";
    wurzel.dataset.bereich = sichtbar;
    for (const [b] of BEREICHE) {
      felder[b].hidden = b !== sichtbar;
      if (b === sichtbar) navLinks[b].setAttribute("aria-current", "page"); else navLinks[b].removeAttribute("aria-current");
    }
    bereichTitel.textContent = TITEL[sichtbar];
    if (opt.url) {
      const ziel = "/einstellungen" + (name ? `?bereich=${name}` : "");
      if (location.pathname + location.search !== ziel) {
        if (opt.url === "ersetzen") history.replaceState(null, "", ziel); else history.pushState(null, "", ziel);
        oberflaeche.urlGeaendert();
      }
    }
    if (opt.einstellung) hervorheben(felder[sichtbar], opt.einstellung);
    else if (opt.fokus) { tid("hauptbereich").scrollTop = 0; if (istMobil()) (name ? bereichTitel : navLinks[sichtbar]).focus(); }
  };

  nav.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-bereich]");
    if (!a || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    zeigen(a.dataset.bereich, { url: "neu", fokus: true });
  });
  zurueck.addEventListener("click", (e) => {
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    zeigen(null, { url: "neu", fokus: true });
  });

  // ---------------------------------------------------------------- Suche
  const suchen = () => {
    const q = sucheFeld.value.trim();
    nav.hidden = !!q;
    treffer.hidden = !q;
    trefferStand.hidden = !q;
    if (!q) { treffer.replaceChildren(); return; }
    const gefunden = VERZEICHNIS.filter(([b, s, titel, mehr]) => passt(q, `${titel} ${mehr} ${TITEL[b]}`)
      && felder[b].querySelector(`[data-einstellung="${s}"]`));
    treffer.replaceChildren(...gefunden.map(([b, s, titel]) => {
      const el = felder[b].querySelector(`[data-einstellung="${s}"]`);
      const k = h("button", { type: "button", class: "einst-treffer-knopf", tid: "einstellungen-treffer-eintrag", "data-bereich": b, "data-einstellung-ziel": s },
        h("span", { class: "einst-nav-titel" }, titel),
        h("span", { class: "einst-status" }, TITEL[b] + (el.closest("details.einst-erweitert") ? " › Erweitert" : "")));
      k.addEventListener("click", () => {
        sucheFeld.value = "";
        suchen();
        zeigen(b, { url: "neu", einstellung: s });
      });
      return h("li", null, k);
    }));
    trefferStand.textContent = gefunden.length === 0 ? "Keine passende Einstellung." : gefunden.length === 1 ? "1 Einstellung gefunden." : `${gefunden.length} Einstellungen gefunden.`;
  };
  sucheFeld.addEventListener("input", suchen);
  sucheFeld.addEventListener("keydown", (e) => {
    const erster = treffer.querySelector("button");
    if (e.key === "Enter" && erster) { e.preventDefault(); erster.click(); }
    else if (e.key === "ArrowDown" && erster) { e.preventDefault(); erster.focus(); }
    else if (e.key === "Escape" && sucheFeld.value) { e.preventDefault(); e.stopPropagation(); sucheFeld.value = ""; suchen(); }
  });
  treffer.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const knoepfe = [...treffer.querySelectorAll("button")];
    const i = knoepfe.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    (e.key === "ArrowDown" ? knoepfe[i + 1] : knoepfe[i - 1] || sucheFeld)?.focus();
  });

  const gewuenscht = new URLSearchParams(suche || "").get("bereich");
  zeigen(TITEL[gewuenscht] ? gewuenscht : null);
  return {
    titel: "Einstellungen",
    // „Einstellungen“ erneut angefordert: auf dem Handy zurück zur Liste der Bereiche
    wiederAngefordert: () => { if (istMobil() && wurzel.dataset.gewaehlt === "ja") zeigen(null, { url: "ersetzen" }); },
  };
}

/** Zur einzelnen Einstellung springen: „Erweitert“ öffnen, in den sichtbaren Bereich rollen, kurz hervorheben. */
function hervorheben(bereich, schluessel) {
  const el = bereich.querySelector(`[data-einstellung="${schluessel}"]`);
  if (!el) return;
  const klappe = el.closest("details");
  if (klappe) klappe.open = true;
  el.scrollIntoView({ block: "center" });
  el.classList.add("einst-gefunden");
  setTimeout(() => el.classList.remove("einst-gefunden"), 2500);
  const ziel = el.matches("input, select, button, a") ? el : el.querySelector("input:not([type=hidden]), select, button, a[href]");
  if (ziel && !ziel.disabled) ziel.focus({ preventScroll: true });
}

// ------------------------------------------------------------------ Allgemein
function allgemein(status, kontext, staende) {
  const thema = h("select", { tid: "einstellung-thema" }, [["system", "wie System"], ["hell", "Hell"], ["dunkel", "Dunkel"]]
    .map(([w, t]) => h("option", { value: w }, t)));
  thema.value = kontext.thema.lesen();
  thema.addEventListener("change", () => { kontext.thema.setzen(thema.value); staende(); });
  const erfolg = h("input", { type: "checkbox", tid: "einstellung-erfolgsmeldung", checked: erfolgsmeldung.lesen() });
  erfolg.addEventListener("change", () => erfolgsmeldung.setzen(erfolg.checked));
  return [
    abschnitt("Darstellung",
      h("div", { "data-einstellung": "design" }, feld("Design", thema)),
      h("div", { "data-einstellung": "erfolgsmeldung" }, h("label", { class: "wahl" }, erfolg,
        " Nach jeder Änderung eine Meldung mit „Rückgängig“ einblenden"),
      h("p", { class: "klein" }, "Ausgeschaltet bleibt Rückgängig über die Pfeile in der Kopfzeile und Strg+Z erreichbar. Gilt für diesen Browser.")),
      h("div", { "data-einstellung": "layout" }, knopf("Layout zurücksetzen", { tid: "layout-zuruecksetzen",
        onclick: () => { layoutZuruecksetzen(); melde("erfolg", "Layout zurückgesetzt."); } }),
      h("p", { class: "klein" }, "Stellt Spaltenbreiten, Sortierung und Panels der Kontoansicht auf die Vorgabe zurück."))),
    abschnitt("Diese Instanz", h("p", { tid: "status-modus", "data-modus": status.modus, "data-einstellung": "betrieb" },
      status.modus === "mock" ? "Mock-Modus" : "Echtbetrieb", ` · Version ${status.version}`,
      status.mock_szenario ? ` · Szenario ${status.mock_szenario}` : "")),
  ];
}

// ------------------------------------------------------------------ Bank
async function bank(zugang, sync, pin, bankStand) {
  const pinStatus = h("p", { tid: "pin-status", class: "einst-pin-status" });
  const verwerfen = knopf("PIN verwerfen", { tid: "pin-verwerfen", onclick: async () => {
    try { await api("DELETE", "/api/sync/pin"); melde("erfolg", "PIN verworfen."); await oberflaeche.neuLaden(); }
    catch (e) { melde("fehler", e.message); }
  } });
  const pinZeigen = () => {
    pinStatus.dataset.vorhanden = pin.vorhanden ? "ja" : "nein";
    pinStatus.textContent = pin.vorhanden ? "Die PIN liegt im Arbeitsspeicher des Servers." : "Keine PIN im Arbeitsspeicher.";
    verwerfen.disabled = !pin.vorhanden;
  };
  pinZeigen();
  pin.gesetzt = () => { pin.vorhanden = true; pinZeigen(); bankStand(); };
  const karte = await bankzugangAbschnitt(zugang, { ...pin, gesetzt: pin.gesetzt, status: pinStatus, verwerfen });
  // ohne einstellbaren Bankzugang (Mock-Modus) steht die PIN in einer eigenen Karte
  return zugang.aenderbar ? [karte] : [karte, h("section", { class: "karte", "data-einstellung": "pin" }, h("h3", null, "Bank-PIN"), pinStatus, verwerfen)];
}

// ------------------------------------------------------------------ Geheimnisse (ntfy-Token, OAuth-Client-Secret)
function geheimnis(geheim, name, titel, schluessel) {
  const gesetzt = geheim.eintraege.some((e) => e.name === name);
  const wert = h("input", { type: "password", tid: `geheimnis-wert-${name}`, autocomplete: "off", value: "" });
  return h("div", { class: "geheimnis", tid: `geheimnis-${name}`, "data-gesetzt": gesetzt ? "ja" : "nein", "data-einstellung": schluessel },
    feld(`${titel} (${gesetzt ? "gesetzt" : "nicht gesetzt"})`, wert),
    knopfLeiste(knopf("Speichern", { tid: `geheimnis-speichern-${name}`, "aria-label": `${titel} speichern`, onclick: async () => {
      const w = wert.value;
      wert.value = "";
      if (!w) { melde("fehler", "Bitte einen Wert eingeben."); return; }
      try { await api("PUT", `/api/geheimnisse/${name}`, { wert: w }); melde("erfolg", `${titel} gespeichert.`); await oberflaeche.neuLaden(); }
      catch (e) { melde("fehler", e.message); }
    } }),
    knopf("Löschen", { tid: `geheimnis-loeschen-${name}`, "aria-label": `${titel} löschen`, onclick: async () => {
      try { await api("DELETE", `/api/geheimnisse/${name}`); melde("erfolg", `${titel} gelöscht.`); await oberflaeche.neuLaden(); }
      catch (e) { melde("fehler", e.message); }
    } })));
}

// ------------------------------------------------------------------ Mail
function mail(postfaecher, geheim) {
  const adresse = h("input", { type: "email", maxlength: "320", autocomplete: "off", tid: "postfach-neu-adresse" });
  return [
    h("section", { class: "karte", "data-einstellung": "postfaecher" }, h("h3", null, "Mail-Postfächer"),
      h("ul", { tid: "postfaecher" }, postfaecher.map((p) => h("li", null,
        h("a", { href: `/mail/postfaecher/${p.id}` }, p.adresse), p.bezeichnung ? ` (${p.bezeichnung})` : ""))),
      postfaecher.length ? h("p", { class: "klein" }, "Zugang (App-Passwort oder OAuth2) und Ordner stehen auf der Seite des Postfachs.")
        : leer("Kein Postfach eingerichtet."),
      h("div", { class: "formular-zeile" }, feld("Neues Postfach (Adresse)", adresse), knopf("Anlegen", { tid: "postfach-neu-anlegen", onclick: async () => {
        try { await aktion(() => api("POST", "/api/mail/postfaecher", { adresse: adresse.value.trim() }), { erfolg: "Postfach angelegt." }); }
        catch (e) { /* gemeldet */ }
      } })),
      h("div", { class: "knopf-leiste", "data-einstellung": "abruf" }, knopf("Mails jetzt abrufen", { tid: "mail-abrufen", onclick: async () => {
        try { await api("POST", "/api/mail/abruf"); await oberflaeche.bestandGeaendert(); melde("erfolg", "Mails abgerufen."); } catch (e) { melde("fehler", e.message); }
      } }))),
    erweitert("mail", "OAuth-Client-Secret", [
      h("p", { class: "klein" }, "Nur nötig, wenn ein Postfach über OAuth2 statt mit einem App-Passwort angemeldet wird."),
      geheimnis(geheim, "oauth_client_secret", "OAuth-Client-Secret", "oauth")]),
  ];
}

// ------------------------------------------------------------------ Benachrichtigungen
function benachrichtigungen(zust, geheim) {
  const ergebnis = h("p", { tid: "benachrichtigung-test-ergebnis", "aria-live": "polite", hidden: true });
  const test = knopf("Test-Benachrichtigung senden", { tid: "benachrichtigung-test", disabled: zust.plugin === "keins",
    onclick: async (e) => {
      const k = e.currentTarget;
      k.disabled = true;
      try {
        const r = await api("POST", "/api/benachrichtigungen/test");
        ergebnis.dataset.zugestellt = r.zugestellt ? "ja" : "nein";
        ergebnis.dataset.gesendet = r.gesendet ? "ja" : "nein";
        ergebnis.textContent = r.zugestellt
          ? (r.gesendet ? "Test-Benachrichtigung zugestellt." : "Mock-Modus: bestätigt, es wurde nichts übertragen.")
          : `Zustellung fehlgeschlagen: ${r.fehler.meldung} (HTTP-Status ${r.fehler.status ?? "keiner"}).`;
      } catch (f) {
        ergebnis.dataset.zugestellt = "nein";
        ergebnis.dataset.gesendet = "nein";
        ergebnis.textContent = `Fehler: ${f.message} (HTTP-Status ${f.status}).`;
      } finally { k.disabled = false; ergebnis.hidden = false; }
    } });
  return [
    h("section", { class: "karte", "data-einstellung": "zustellung" }, h("h3", null, "Zustellung"),
      h("p", { tid: "zustellung-status", "data-plugin": zust.plugin },
        `Zustellung über: ${zust.plugin} · ausstehend ${zust.ausstehend}, zugestellt ${zust.zugestellt}, aufgegeben ${zust.aufgegeben}`),
      zust.letzter_fehler ? h("p", { class: "klein" }, "Letzter Fehler: ", zust.letzter_fehler.meldung || "") : null, test, ergebnis),
    abschnitt("Zugang zu ntfy", h("p", { class: "klein" }, "Nur nötig, wenn das ntfy-Thema mit einem Token geschützt ist."),
      geheimnis(geheim, "ntfy_token", "ntfy-Token", "ntfy")),
  ];
}

// ------------------------------------------------------------------ Sicherheit
function sicherheit(schutz, kontext) {
  const teile = [];
  if (anmeldung.aktiv) {
    const alt = h("input", { type: "password", autocomplete: "current-password", tid: "passwort-alt" });
    const neu = h("input", { type: "password", autocomplete: "new-password", tid: "passwort-neu" });
    teile.push(abschnitt("Anmeldung",
      h("div", { class: "formular-zeile", "data-einstellung": "passwort" }, feld("Bisheriges Passwort", alt),
        feld("Neues Passwort", neu), knopf("Passwort ändern", { tid: "passwort-aendern", onclick: async () => {
          try { await api("PUT", "/api/anmeldung/passwort", { altes_passwort: alt.value, neues_passwort: neu.value }); melde("erfolg", "Passwort geändert."); }
          catch (e) { melde("fehler", e.message); } finally { alt.value = ""; neu.value = ""; }
        } })),
      h("div", { class: "knopf-leiste", "data-einstellung": "abmelden" }, knopf("Abmelden", { tid: "abmelden", onclick: () => kontext.abmelden() }))));
  } else {
    teile.push(abschnitt("Anmeldung", h("p", null, "Diese Instanz läuft ohne Anmeldung.")));
  }
  if (schutz) teile.push(schutzAbschnitt(schutz));
  return teile;
}

/* D-129: Schutz der Geheimnisse mit dem Login-Passwort */
function schutzAbschnitt(st) {
  const pw = h("input", { type: "password", tid: "schutz-passwort", autocomplete: "current-password" });
  const mitPasswort = (pfad, erfolg) => async () => {
    const wert = pw.value;
    pw.value = "";
    if (!wert) { melde("fehler", "Bitte das Login-Passwort eingeben."); return; }
    try { await api("POST", pfad, { passwort: wert }); melde("erfolg", erfolg); window.dispatchEvent(new Event("kontor-sperre")); await oberflaeche.neuLaden(); }
    catch (e) { melde("fehler", e.message); }
  };
  const text = !st.aktiv
    ? "Aus: Geheimnisse sind nur mit dem Systemschlüssel verschlüsselt. Eingeschaltet schützt das Login-Passwort Bank-PIN und Mail-Zugänge zusätzlich – auch in Snapshots der Festplatte. Nach jedem Neustart muss Kontor dann einmal entsperrt werden (beim Login automatisch)."
    : st.entsperrt ? `Ein und entsperrt: ${st.geschuetzt} Geheimnis(se) mit dem Login-Passwort geschützt${st.pin_gemerkt ? ", Bank-PIN gemerkt" : ""}.`
      : "Ein, aber gesperrt: Bankabruf und Mail-Abgleich warten auf das Entsperren.";
  const knoepfe = !st.aktiv
    ? [knopf("Schutz einschalten", { tid: "schutz-einschalten", class: "knopf knopf-haupt",
      onclick: mitPasswort("/api/geheimnisse/schutz", "Die Geheimnisse sind jetzt mit dem Login-Passwort geschützt.") })]
    : [st.entsperrt
      ? knopf("Jetzt sperren", { tid: "schutz-sperren", onclick: async () => {
        try { await api("POST", "/api/geheimnisse/sperren", {}); melde("erfolg", "Gesperrt."); window.dispatchEvent(new Event("kontor-sperre")); await oberflaeche.neuLaden(); }
        catch (e) { melde("fehler", e.message); }
      } })
      : knopf("Entsperren", { tid: "schutz-entsperren", class: "knopf knopf-haupt",
        onclick: mitPasswort("/api/geheimnisse/entsperren", "Entsperrt.") }),
    st.pin_gemerkt ? knopf("Gemerkte PIN vergessen", { tid: "schutz-pin-vergessen", onclick: async () => {
      try { await api("DELETE", "/api/sync/pin/gemerkt"); melde("erfolg", "Gemerkte PIN gelöscht."); await oberflaeche.neuLaden(); }
      catch (e) { melde("fehler", e.message); }
    } }) : null,
    knopf("Schutz ausschalten", { tid: "schutz-ausschalten", class: "knopf knopf-gefahr",
      onclick: mitPasswort("/api/geheimnisse/schutz/ausschalten", "Der Schutz ist ausgeschaltet.") })];
  return h("section", { class: "karte", "data-einstellung": "schutz" }, h("h3", null, "Schutz der Geheimnisse"),
    h("p", { tid: "schutz-status", "data-aktiv": st.aktiv ? "ja" : "nein", "data-gesperrt": st.gesperrt ? "ja" : "nein" }, text),
    feld("Login-Passwort", pw), h("div", { class: "knopf-leiste" }, ...knoepfe.filter(Boolean)));
}

// ------------------------------------------------------------------ Daten und Sicherung
function daten() {
  const datei = h("input", { type: "file", tid: "sicherung-datei", accept: ".zip,application/zip" });
  const ausgabe = h("div", { "aria-live": "polite" });
  const senden = (params) => {
    const fd = new FormData();
    fd.append("datei", datei.files[0], datei.files[0].name);
    return api("POST", "/api/sicherung/einspielen" + abfrage(params), undefined, { formular: fd });
  };
  const einspielen = knopf("Einspielen …", { tid: "sicherung-einspielen", class: "knopf knopf-gefahr", disabled: true,
    onclick: async (e) => {
      if (!(await bestaetigen("Den gesamten Buchbestand durch die Sicherung ersetzen?", { ja: "Bestand ersetzen", ausloeser: e.currentTarget }))) return;
      try { await aktion(() => senden({ bestaetigt: true }), { erfolg: "Sicherung eingespielt." }); } catch (f) { /* gemeldet */ }
    } });
  const pruefen = knopf("Prüfen", { tid: "sicherung-pruefen", onclick: async () => {
    if (!datei.files.length) { melde("fehler", "Bitte zuerst eine Sicherungsdatei wählen."); return; }
    try {
      const r = await senden({ trocken: true });
      ausgabe.replaceChildren(h("p", null, r.geaendert ? "Die Sicherung ist gültig; Einspielen ersetzt den Bestand."
        : "Die Sicherung ist identisch mit dem Bestand.", ` (erstellt ${zeitText(r.manifest.erstellt)})`));
      einspielen.disabled = !r.geaendert;
    } catch (f) { ausgabe.replaceChildren(h("p", { class: "fehler", role: "alert" }, f.message)); einspielen.disabled = true; }
  } });
  const tags = stamm.tags.length ? h("ul", null, stamm.tags.slice().sort(nachName).map((t) => h("li", null,
    `${t.name} (${t.anzahl_buchungen} Buchungen) `,
    knopf("Umbenennen…", { "aria-label": `Tag ${t.name} umbenennen`, onclick: (e) => dialog("tag-dialog", `Tag „${t.name}“ umbenennen`, (inhalt, d) => {
      const n = h("input", { type: "text", value: t.name, maxlength: "200" });
      const ok = knopf("Speichern", { class: "knopf knopf-haupt" });
      ok.addEventListener("click", () => imDialog(d, ok, () => aktion(() => api("PATCH", `/api/tags/${t.id}`, { name: n.value.trim() }),
        { stillBeiFehler: true, danach: () => d.schliessen(true), erfolg: "Tag umbenannt." })));
      inhalt.append(feld("Name", n), knopfLeiste(ok, knopf("Abbrechen", { onclick: () => d.schliessen(null) })));
    }, { ausloeser: e.currentTarget }) }),
    knopf("Löschen", { "aria-label": `Tag ${t.name} löschen`, onclick: async (e) => {
      if (!(await bestaetigen(`Tag „${t.name}“ löschen?`, { ja: "Löschen", ausloeser: e.currentTarget }))) return;
      try { await aktion(() => api("DELETE", `/api/tags/${t.id}`), { erfolg: "Tag gelöscht." }); } catch (f) { /* gemeldet */ }
    } })))) : leer("Noch keine Tags.");
  return [
    abschnitt("Datensicherung",
      h("div", { "data-einstellung": "sicherungspunkte" }, h("p", null, "Kontor sichert stündlich, wenn sich etwas geändert hat, "
        + "und hält ältere Stände je Tag, Woche und Monat. Jeder Stand lässt sich wiederherstellen und herunterladen."),
      h("p", null, h("a", { tid: "sicherungspunkte-link", href: "/sicherung", class: "knopf knopf-haupt" }, "Sicherungspunkte öffnen"))),
      h("div", { "data-einstellung": "sicherung" }, h("p", null, h("a", { tid: "sicherung-herunterladen", href: "/api/sicherung", download: "",
        class: "knopf" }, "Sicherung herunterladen")),
      h("p", { class: "klein" }, "Enthält den gesamten Buchbestand, aber keine Geheimnisse (PIN, Passwörter, Tokens).")),
      h("div", { class: "einst-gruppe", "data-einstellung": "einspielen" }, h("h4", null, "Sicherung einspielen"),
        feld("Sicherungsdatei", datei), knopfLeiste(pruefen, einspielen), ausgabe)),
    h("section", { class: "karte", "data-einstellung": "tags" }, h("h3", null, "Tags"), tags),
  ];
}
