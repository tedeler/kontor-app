/* Kontor – Passkeys und Bildschirmsperre (Feature „passkeys“, D-284; sicherheit.md 13, oberflaeche.md 45).
 *
 * Passkey: Der Browser fragt den Authentikator des Geräts (Fingerabdruck, Gesicht oder Gerätesperre); zum Server geht
 * nur die signierte Aufgabe. Bildschirmsperre: gilt je Gerät (Sitzung); der Server sperrt die Sitzung nach der
 * gewählten Zeit ohne Anfrage und antwortet dann mit 423, bis sie mit Passkey oder Passwort entsperrt ist. Die
 * Oberfläche legt dann ein deckendes Blatt über alles – auch sofort beim Zurückholen, bevor der Server gefragt ist. */
import { ApiFehler, anmeldung, anmeldungLaden, api, h, tid } from "./kern.js";
import { knopf } from "./ui.js";

const SPEICHER = "kontor.bildschirmsperre";     // gewählte Minuten dieses Geräts ("aus" oder Zahl)
export const SPERRE_WAHL = [[null, "Aus"], [0, "Sofort beim Verlassen"], [1, "Nach 1 Minute"], [5, "Nach 5 Minuten"],
  [15, "Nach 15 Minuten"], [60, "Nach 1 Stunde"]];

export const passkeysMoeglich = () => !!(window.isSecureContext && window.PublicKeyCredential && navigator.credentials);

const b64 = (puffer) => btoa(String.fromCharCode(...new Uint8Array(puffer))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const roh = (text) => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const kennungen = (liste) => (liste || []).map((c) => ({ ...c, id: roh(c.id) }));

/** Text für einen Fehler des Authentikators (Abbruch durch die Person ist kein Fehler: null). */
export function passkeyFehlerText(e) {
  if (e instanceof ApiFehler) return e.message;
  if (e && (e.name === "NotAllowedError" || e.name === "AbortError")) return null;
  if (e && e.name === "InvalidStateError") return "Dieses Gerät hat schon einen Passkey für Kontor.";
  if (e && e.name === "SecurityError") return "Passkeys gehen nur über HTTPS und unter dem Namen dieser Instanz.";
  return (e && e.message) || "Der Passkey konnte nicht verwendet werden.";
}

/** Passkey auf diesem Gerät anlegen und beim Server eintragen. */
export async function passkeyAnlegen(name) {
  const o = await api("POST", "/api/passkeys/optionen");
  const cred = await navigator.credentials.create({ publicKey: { ...o, challenge: roh(o.challenge),
    user: { ...o.user, id: roh(o.user.id) }, excludeCredentials: kennungen(o.excludeCredentials) } });
  const r = cred.response;
  const schluessel = r.getPublicKey && r.getAuthenticatorData ? r.getPublicKey() : null;
  if (!schluessel) throw new Error("Dieser Browser liefert den Schlüssel des Passkeys nicht (zu alt oder unbekanntes Verfahren).");
  return api("POST", "/api/passkeys", { name, kennung: b64(cred.rawId), alg: r.getPublicKeyAlgorithm(),
    schluessel: b64(schluessel), client_daten: b64(r.clientDataJSON), auth_daten: b64(r.getAuthenticatorData()) });
}

/** Aufgabe des Servers vom Authentikator signieren lassen (Anmelden, Entsperren). */
export async function passkeyAntwort(o) {
  const cred = await navigator.credentials.get({ publicKey: { ...o, challenge: roh(o.challenge),
    allowCredentials: kennungen(o.allowCredentials) } });
  const r = cred.response;
  return { kennung: b64(cred.rawId), client_daten: b64(r.clientDataJSON), auth_daten: b64(r.authenticatorData),
    signatur: b64(r.signature) };
}

// ------------------------------------------------------------------ Wahl dieses Geräts
function gemerkt() {
  try {
    const w = localStorage.getItem(SPEICHER);
    if (w === null) return undefined;
    return w === "aus" ? null : Number(w);
  } catch (e) { return undefined; }
}

export async function sperreWaehlen(minuten) {
  const st = await api("PUT", "/api/anmeldung/bildschirmsperre", { minuten });
  anmeldung.bildschirmsperre = st.bildschirmsperre;
  try { localStorage.setItem(SPEICHER, minuten === null ? "aus" : String(minuten)); } catch (e) { /* ohne Speicher */ }
  return st;
}

export const sperreMinuten = () => (anmeldung.bildschirmsperre ? anmeldung.bildschirmsperre.minuten : null);

// ------------------------------------------------------------------ Sperrblatt
let blatt = null;
let danach = async () => {};
let wartende = [];
let verborgenSeit = null;

export const istGesperrt = () => !!blatt;
/** Erfüllt sich, sobald entsperrt ist (sofort, wenn nicht gesperrt). */
export const entsperrt = () => (blatt ? new Promise((r) => wartende.push(r)) : Promise.resolve());

function sperreZeigen() {
  if (blatt || !anmeldung.aktiv) return;
  const fehler = h("p", { class: "sperre-fehler", tid: "sperre-fehler", role: "alert", hidden: true });
  const zeige = (text) => { fehler.textContent = text || ""; fehler.hidden = !text; };
  const passwort = h("input", { type: "password", autocomplete: "current-password", tid: "sperre-passwort",
    "aria-label": "Haushaltspasswort" });
  const mitPasskey = passkeysMoeglich() && anmeldung.passkeys;
  let laeuft = false;
  const versuchen = async (holen) => {
    if (laeuft) return;
    laeuft = true;
    zeige("");
    try {
      const st = await api("POST", "/api/anmeldung/entsperren", await holen());
      anmeldung.bildschirmsperre = st.bildschirmsperre;
      anmeldung.csrf = st.csrf_token || anmeldung.csrf;
      sperreAufheben();
    } catch (e) {
      const text = passkeyFehlerText(e);
      if (text) zeige(e instanceof ApiFehler && e.code === "passkey_ungueltig" ? "Der Passkey wurde nicht anerkannt." : text);
      passwort.value = "";
    } finally { laeuft = false; }
  };
  const perPasskey = () => versuchen(async () => passkeyAntwort(await api("POST", "/api/anmeldung/entsperren/optionen")));
  const formular = h("form", { class: "sperre-passwort", hidden: mitPasskey },
    passwort, knopf("Mit Passwort entsperren", { tid: "sperre-passwort-knopf", type: "submit" }));
  formular.addEventListener("submit", (e) => { e.preventDefault(); if (passwort.value) versuchen(async () => ({ passwort: passwort.value })); });
  blatt = h("div", { class: "bildschirmsperre", tid: "bildschirmsperre", role: "dialog", "aria-modal": "true",
    "aria-labelledby": "bildschirmsperre-titel" },
    h("div", { class: "sperre-karte" },
      h("img", { src: "/oeffentlich/icon.svg", alt: "", width: "56", height: "56" }),
      h("h2", { id: "bildschirmsperre-titel" }, "Kontor ist gesperrt"),
      mitPasskey ? knopf("Entsperren", { tid: "sperre-entsperren", class: "knopf knopf-haupt", onclick: perPasskey }) : null,
      mitPasskey ? knopf("Stattdessen mit Passwort", { tid: "sperre-passwort-zeigen", class: "knopf",
        onclick: (e) => { formular.hidden = false; e.currentTarget.hidden = true; passwort.focus(); } }) : null,
      formular, fehler,
      knopf("Abmelden", { tid: "sperre-abmelden", class: "knopf sperre-abmelden", onclick: async () => {
        try { await api("POST", "/api/anmeldung/abmelden"); } catch (e) { /* trotzdem zur Anmeldeseite */ }
        location.assign("/anmelden");
      } })));
  const app = tid("app");
  if (app) app.inert = true;                       // nichts darunter ist bedien- oder fokussierbar
  document.querySelectorAll(".dialog-huelle, .kontextmenue").forEach((el) => { el.inert = true; });
  document.body.append(blatt);
  (mitPasskey ? tid("sperre-entsperren", blatt) : passwort).focus();
  // Der Fingerabdruck wird gleich angeboten, wenn die Seite sichtbar ist (manche Browser verlangen dafür einen Tipp)
  if (mitPasskey && document.visibilityState === "visible") perPasskey();
}

function sperreAufheben() {
  if (!blatt) return;
  blatt.remove();
  blatt = null;
  const app = tid("app");
  if (app) app.inert = false;
  document.querySelectorAll(".dialog-huelle, .kontextmenue").forEach((el) => { el.inert = false; });
  const warten = wartende;
  wartende = [];
  warten.forEach((r) => r());
  danach().catch(() => { /* gemeldet */ });
}

/** Einmal beim Start: Ereignisse verdrahten, die Wahl dieses Geräts auf die (neue) Sitzung übertragen und – wenn der
 *  Server die Sitzung schon gesperrt meldet – das Sperrblatt zeigen. `nachEntsperren` lädt die Ansicht neu. */
export async function sperreEinrichten(nachEntsperren) {
  danach = nachEntsperren;
  window.addEventListener("kontor-bildschirmsperre", sperreZeigen);
  document.addEventListener("visibilitychange", () => {
    const minuten = sperreMinuten();
    if (document.visibilityState === "hidden") {
      verborgenSeit = Date.now();
      if (minuten === 0 && !blatt) {
        // „sofort“: Blatt schon jetzt (kein Blick auf die Daten beim Zurückholen) und dem Server melden
        sperreZeigen();
        fetch("/api/anmeldung/sperren", { method: "POST", credentials: "same-origin", keepalive: true,
          headers: anmeldung.csrf ? { "X-Kontor-CSRF": anmeldung.csrf } : {} }).catch(() => { /* Rückhalt: 90 s */ });
      }
      return;
    }
    if (minuten !== null && verborgenSeit !== null && Date.now() - verborgenSeit > minuten * 60000) sperreZeigen();
    verborgenSeit = null;
    if (blatt && anmeldung.passkeys && passkeysMoeglich() && !tid("sperre-fehler", blatt).textContent) tid("sperre-entsperren", blatt)?.click();
    else if (anmeldung.aktiv && minuten !== null) anmeldungLaden().catch(() => { /* offline: der Hinweis genügt */ });
  });
  if (!anmeldung.aktiv) return;
  const wahl = gemerkt();
  if (wahl !== undefined && wahl !== sperreMinuten() && !(anmeldung.bildschirmsperre || {}).gesperrt) {
    try { await sperreWaehlen(wahl); } catch (e) { /* bleibt wie auf dem Server */ }
  }
  if ((anmeldung.bildschirmsperre || {}).gesperrt) sperreZeigen();
}
