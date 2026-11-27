/* Kontor – Kurztext zum Teilen einer Buchung (D-304, Gestaltung D-306, oberflaeche.md 50).
 * Gesetzt für WhatsApp und ähnliche Dienste: *fett* für Empfänger und Betrag, eine Zeile je Angabe mit Symbol,
 * der lesbare Teil des Verwendungszwecks als Zitat „> …“, zuletzt allein der Link (damit er klickbar erkannt wird).
 * Reine Funktion ohne DOM; Texte aus dem Buchbestand werden so entschärft, dass sie die Auszeichnung nicht stören.
 */
import { betragText } from "./kern.js";
import { zweckZerlegen } from "./zweck.js";

const ZWECK_MAX = 140;
const WOCHENTAGE = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const ARTEN = { ausgabe: "Ausgabe", einnahme: "Einnahme", umbuchung: "Umbuchung" };
// Auszeichnungszeichen von WhatsApp durch ähnlich aussehende Zeichen ersetzen (∗ ˍ ∼ ˋ)
const ERSATZ = { "*": "∗", _: "ˍ", "~": "∼", "`": "ˋ" };

/** Text aus dem Buchbestand: Leerraum zusammengefasst, Auszeichnungszeichen entschärft. */
export function entschaerfen(text) {
  return String(text ?? "").replace(/\s+/g, " ").trim().replace(/[*_~`]/g, (c) => ERSATZ[c]);
}

function datumMitTag(iso) {
  const s = String(iso || "").slice(0, 10);
  const [j, m, t] = s.split("-");
  if (!t) return "";
  const d = new Date(`${s}T12:00:00Z`);
  const tag = Number.isNaN(d.getTime()) ? "" : `${WOCHENTAGE[d.getUTCDay()]}, `;
  return `${tag}${t}.${m}.${j}`;
}

/** Betrag mit Vorzeichen: „−23,40 €“, „+1.234,56 €“ (geschütztes Leerzeichen vor €). */
function betragMitVorzeichen(cent) {
  const t = betragText(cent);
  if (cent < 0) return "−" + t.slice(1);
  return cent > 0 ? "+" + t : t;
}

/** Lesbarer Teil des Verwendungszwecks (ohne SEPA-Kennungen), gekürzt; leer, wenn er nur den Empfänger wiederholt. */
function zweckKurz(zweck, empfaenger) {
  const z = zweckZerlegen(String(zweck ?? ""));
  let t = entschaerfen(z.texte.join(" · "));
  if (!t || t.toLowerCase() === entschaerfen(empfaenger).toLowerCase()) return "";
  if (t.length > ZWECK_MAX) t = t.slice(0, ZWECK_MAX - 1).trimEnd() + "…";
  return t;
}

/**
 * @param {{empfaenger?: string, betrag: number, art: "ausgabe"|"einnahme"|"umbuchung", datum: string, konto: string,
 *          kategorie?: string, tags?: string[], zweck?: string, link: string}} a
 * @returns {string} Kurztext, Zeilen getrennt durch „\n“
 */
export function teilenText(a) {
  const name = entschaerfen(a.empfaenger) || "Buchung";
  const art = ARTEN[a.art] || "";
  const zeilen = [`*${name}*`, `*${betragMitVorzeichen(a.betrag)}*${art ? ` · ${art}` : ""}`, ""];
  const datum = datumMitTag(a.datum);
  if (datum) zeilen.push(`📅 ${datum}`);
  const konto = entschaerfen(a.konto);
  if (konto) zeilen.push(`🏦 ${konto}`);
  const kategorie = entschaerfen(a.kategorie);
  if (kategorie) zeilen.push(`🏷️ ${kategorie}`);
  const tags = (a.tags || []).map(entschaerfen).filter(Boolean);
  if (tags.length) zeilen.push(`🔖 ${tags.join(", ")}`);
  const zweck = zweckKurz(a.zweck, a.empfaenger);
  if (zweck) zeilen.push("", `> ${zweck}`);
  zeilen.push("", a.link);
  return zeilen.join("\n");
}
