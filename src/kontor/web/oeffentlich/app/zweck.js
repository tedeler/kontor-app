/* Kontor – Lesbare Darstellung des Verwendungszwecks (nur Anzeige, D-175).
 * Banken liefern den Verwendungszweck oft als aneinandergeklebte Zeilen ohne Trenner
 * („LASTSCHRIFT / BELASTUNGCAFE …“). zweckZerlegen() erkennt bekannte Bestandteile
 * (Buchungsart, SEPA-Schlüssel, Karte, Zeitpunkt, Referenz) und liefert eine Gliederung.
 * Der gespeicherte Text bleibt unverändert; Unerkanntes bleibt als Text stehen. */

/** SEPA-Schlüssel nach DFÜ-Abkommen (Anlage 3). SVWZ ist der eigentliche Verwendungszweck. */
const SEPA = {
  EREF: "Ende-zu-Ende-Referenz", KREF: "Kundenreferenz", MREF: "Mandatsreferenz", CRED: "Gläubiger-ID",
  DEBT: "Zahler-ID", ABWA: "Abweichender Auftraggeber", ABWE: "Abweichender Empfänger", IBAN: "IBAN",
  BIC: "BIC", PURP: "Zweck-Code", COAM: "Zinskompensation", OAMT: "Ursprungsbetrag", SVWZ: "",
};
/** Ausgeschriebene Schlüssel, wie manche Banken (z. B. comdirect) sie in den Text setzen. */
const WORTSCHLUESSEL = [
  ["END-TO-END-REF\\.?:", "Ende-zu-Ende-Referenz"], ["MANDATSREF\\.?:", "Mandatsreferenz"],
  ["GLÄUBIGER-ID:", "Gläubiger-ID"], ["GLAEUBIGER-ID:", "Gläubiger-ID"], ["KUNDENREFERENZ:", "Kundenreferenz"],
];
// Schlüssel trennen den Text in Abschnitte; „Ref.“ der Bank steht meist am Ende und beendet den Wert davor.
const SCHLUESSEL_RE = new RegExp([
  `(?<![A-Za-z])(${Object.keys(SEPA).join("|")})\\+`,
  ...WORTSCHLUESSEL.map(([re]) => `(${re})`),
  "(?<![A-Za-z])(Ref\\.)\\s?",
].join("|"), "g");
const WERTLOS = new Set(["NOTPROVIDED", "NICHT ANGEGEBEN"]);
const VERFAHREN = { CORE: "Basislastschrift (CORE)", B2B: "Firmenlastschrift (B2B)", COR1: "Basislastschrift (COR1)" };

function schluesselName(m) {
  if (m[1]) return { sepa: m[1], name: SEPA[m[1]] };
  for (let i = 0; i < WORTSCHLUESSEL.length; i += 1) if (m[i + 2]) return { name: WORTSCHLUESSEL[i][1] };
  return { name: "Referenz", ref: true };
}

/** Buchungsarten, wie Banken sie dem Zweck voranstellen (längere zuerst). */
const ARTEN = [
  "LASTSCHRIFT / BELASTUNG", "ÜBERWEISUNG / GUTSCHRIFT", "UEBERWEISUNG / GUTSCHRIFT", "SEPA-LASTSCHRIFT",
  "SEPA-ÜBERWEISUNG", "SEPA-UEBERWEISUNG", "SEPA-GUTSCHRIFT", "ERSTLASTSCHRIFT", "FOLGELASTSCHRIFT",
  "KARTENZAHLUNG", "BARGELDAUSZAHLUNG", "GELDAUTOMAT", "DAUERAUFTRAG", "LASTSCHRIFT", "BELASTUNG", "GUTSCHRIFT",
  "ÜBERWEISUNG", "UEBERWEISUNG", "ECHTZEITÜBERWEISUNG", "LOHN, GEHALT, RENTE", "LOHN/GEHALT", "ABSCHLUSS",
  "ENTGELTABSCHLUSS", "RÜCKLASTSCHRIFT", "RUECKLASTSCHRIFT", "AUSZAHLUNG", "EINZAHLUNG",
];
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
// links: Textanfang oder kein Buchstabe; rechts: kein Kleinbuchstabe (aneinandergeklebte Großbuchstaben erlaubt)
const ARTEN_RE = new RegExp(`(?<![A-Za-zÄÖÜäöüß])(${ARTEN.map(esc).join("|")})(?![a-zäöüß])`, "g");

const MUSTER = [
  // Kartennummer (oft maskiert): „KARTE NR. 4871 78XX XXXX 7509“
  { art: "karte", re: /KARTE NR\.?\s?([0-9X]{4}(?: ?[0-9X]{2,4}){2,4})/g },
  // Kartenprodukt: „COMDIRECT VISA-DEBITKARTE“, „GIROCARD“
  { art: "kartenart", re: /(?<![A-Za-z])[A-ZÄÖÜ][A-ZÄÖÜ ]{0,30}?(?:VISA|MASTERCARD|GIROCARD|MAESTRO|V PAY|DEBITKARTE)[A-Z-]*/g },
  // ISO-Zeitpunkt: „2026-11-11 00:00:00“
  { art: "zeitpunkt", re: /(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::\d{2})?)?/g },
  // Amazon-Bestellnummer „302-1234567-1234567“ (auch teilweise maskiert)
  { art: "bestellung", re: /(?<![\dx])[\dx]{3}-[\dx]{7,8}-[\dx]{7}(?![\dx])/g },
];

const LABEL = { karte: "Karte", kartenart: "Kartenart", zeitpunkt: "Zeitpunkt", bestellung: "Bestellnummer" };

function artText(s) {
  return s.toLowerCase().replace(/(^|[\s/,-])([a-zäöü])/g, (_, a, b) => a + b.toUpperCase());
}

function zeitText(m) {
  const d = `${m[3]}.${m[2]}.${m[1]}`;
  return m[4] !== undefined && !(m[4] === "00" && m[5] === "00") ? `${d}, ${m[4]}:${m[5]} Uhr` : d;
}

/** Bereiche [von, bis) mit Art; überlappende spätere Treffer werden verworfen. */
function bereiche(text) {
  const b = [];
  const frei = (von, bis) => b.every((x) => bis <= x.von || von >= x.bis);
  for (const m of text.matchAll(ARTEN_RE)) b.push({ von: m.index, bis: m.index + m[0].length, art: "buchungsart", wert: artText(m[1]) });
  // erkannte Buchungsarten maskieren, damit spätere Muster nicht über sie hinweg greifen
  let maske = text;
  for (const x of b) maske = maske.slice(0, x.von) + "\u0001".repeat(x.bis - x.von) + maske.slice(x.bis);
  for (const { art, re } of MUSTER) {
    for (const m of maske.matchAll(re)) {
      const von = m.index;
      const bis = von + m[0].length;
      if (!frei(von, bis)) continue;
      const wert = art === "zeitpunkt" ? zeitText(m) : art === "kartenart" ? m[0].trim() : (m[1] || m[0]).trim();
      b.push({ von, bis, art, wert });
    }
  }
  return b.sort((x, y) => x.von - y.von);
}

const nurZeichen = (s) => !/[A-Za-z0-9ÄÖÜäöüß]/.test(s);

/** Zerlegt einen freien Textabschnitt (ohne SEPA-Schlüssel). */
function abschnitt(text, aus) {
  let pos = 0;
  for (const x of bereiche(text)) {
    const davor = paypal(text.slice(pos, x.von), aus).trim();
    if (davor && !nurZeichen(davor)) aus.texte.push(davor);
    if (x.art === "buchungsart") { if (!aus.arten.includes(x.wert)) aus.arten.push(x.wert); }
    else aus.angaben.push({ art: x.art, name: LABEL[x.art], wert: x.wert, mono: x.art === "karte" || x.art === "bestellung" });
    pos = x.bis;
  }
  const rest = paypal(text.slice(pos), aus).trim();
  if (rest && !nurZeichen(rest)) aus.texte.push(rest);
}

/** PayPal: „<Kennung>/PP.<Nr>.PP/. <Händler>, IHR EINKAUF BEI <Händler>“. */
function paypal(text, aus) {
  const m = /^\s*(\S+)\/PP\.(\S+?)\.PP\/\.\s*/.exec(text);
  if (!m) return text;
  if (!aus.arten.includes("PayPal")) aus.arten.push("PayPal");
  aus.angaben.push({ art: "paypal", name: "PayPal-Referenz", wert: `${m[1]} / ${m[2]}`, mono: true });
  let rest = text.slice(m[0].length);
  const einkauf = /^(.+?),?\s*IHR EINKAUF BEI\s+(.+)$/i.exec(rest);
  if (einkauf) rest = einkauf[1].trim() === einkauf[2].trim() ? `Einkauf bei ${einkauf[2].trim()}` : rest;
  return rest;
}

/** Wert hinter einem Schlüssel: Trenner „ / “ am Ende ab, Lastschriftverfahren (CORE, B2B) als eigene Angabe. */
function schluesselWert(roh, aus) {
  let wert = roh.trim().replace(/\s*\/\s*$/, "");
  const v = /^(.*?)(CORE|B2B|COR1)$/.exec(wert);
  if (v && /\/\s*$/.test(roh.trim())) {
    wert = v[1].trim();
    aus.verfahren = { art: "verfahren", name: "Lastschriftverfahren", wert: VERFAHREN[v[2]], mono: false };
  }
  return wert;
}

/**
 * @returns {{arten: string[], texte: string[], angaben: {art, name, wert, mono}[], erkannt: boolean}}
 * texte: der eigentliche Zweck (in Reihenfolge), angaben: erkannte Bestandteile mit Bezeichnung.
 */
export function zweckZerlegen(original) {
  const text = (original || "").replace(/\s+/g, " ").trim();
  const aus = { arten: [], texte: [], angaben: [], erkannt: false };
  if (!text) return aus;
  const schluessel = [...text.matchAll(SCHLUESSEL_RE)];
  const frei = (t) => abschnitt(t, aus);
  if (schluessel.length) {
    frei(text.slice(0, schluessel[0].index));
    const angaben = [];
    schluessel.forEach((m, i) => {
      const roh = text.slice(m.index + m[0].length, i + 1 < schluessel.length ? schluessel[i + 1].index : text.length);
      const s = schluesselName(m);
      if (s.sepa === "SVWZ") { frei(roh.trim()); return; }
      const wert = schluesselWert(roh, aus);
      if (!wert || WERTLOS.has(wert.toUpperCase())) return;
      angaben.push({ art: s.sepa ? s.sepa.toLowerCase() : s.ref ? "referenz" : "schluessel", name: s.name, wert,
        mono: s.sepa !== "ABWA" && s.sepa !== "ABWE" });
    });
    aus.angaben.push(...angaben);
    if (aus.verfahren) aus.angaben.push(aus.verfahren);
    delete aus.verfahren;
    // Kennungen, die schon als Angabe erscheinen, nicht noch einmal im Text zeigen (z. B. Ende-zu-Ende-Referenz)
    const werte = new Set(angaben.map((a) => a.wert).filter((w) => w.length >= 8));
    aus.texte = aus.texte.map((t) => t.split(" ").filter((w) => !werte.has(w)).join(" ")).filter((t) => t && !nurZeichen(t));
  } else {
    frei(text);
  }
  aus.erkannt = aus.arten.length > 0 || aus.angaben.length > 0;
  if (!aus.erkannt) aus.texte = [text];   // nichts erkannt: Text unverändert (nur Leerraum vereinheitlicht)
  return aus;
}
