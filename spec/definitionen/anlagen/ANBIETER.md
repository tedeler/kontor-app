# Anbieter-Beschreibungen für den Abgleich von Mails und Buchungen

Kontor erkennt Bestell- und Zahlungsmails und ordnet sie Bankbuchungen zu. Was dabei von einem Anbieter abhängt
(Amazon, PayPal, …), steht in einer **Beschreibung**: einer TOML-Datei mit regulären Ausdrücken. Der Abgleich
selbst (erwartete Zahlungen, Zuordnen in Stufen, Mails als Dokumente anhängen, Anzeige) ist für alle gleich.

- Mitgeliefert werden die Beschreibungen `amazon.toml` und `paypal.toml`.
- Eigene Beschreibungen: Dateien `*.toml` in einem Verzeichnis, das `KONTOR_ANBIETER_VERZEICHNIS` nennt
  (Konfiguration `anbieter_verzeichnis`). Sie werden beim nächsten Abgleich gelesen; geänderte Dateien ohne
  Neustart. Eine Datei mit dem `name` eines mitgelieferten Anbieters ersetzt diesen.
- Eine fehlerhafte Datei wird übergangen; das Protokoll nennt Datei und Stelle
  („Anbieter-Beschreibung kaufhaus.toml wird übergangen: art[0].gesamt: …“).

## Aufbau

```toml
name = "kaufhaus"                       # Kleinbuchstaben, Ziffern, _ ; steht an der erwarteten Zahlung
titel = "Kaufhaus Muster"               # Händlername, wenn die Mail keinen eigenen nennt
absender = '(^|\.)kaufhaus\.example$'   # Ausdruck auf die Domain des Absenders (klein geschrieben)

[kennung]                               # Pflicht: ohne Kennung wird die Mail nicht gelesen
muster = 'Auftrag\s+(K\d{6})'           # Gruppe 1 ist die Kennung
suche_in = ["betreff", "text"]          # in dieser Reihenfolge; Vorgabe ["text"]

[[art]]                                 # Mailarten; die erste, deren Betreff passt, gilt
name = "bestellung"
rolle = "ausgabe"                       # ausgabe | erstattung | storno
grund = "bestellung"                    # nur bei ausgabe: bestellung | paypal
betreff = '(?i)auftragsbestätigung'
gesamt = { betrag_nach = '(?i)zu zahlen' }      # Pflicht; fehlt der Betrag, wird die Mail nicht gelesen
guthaben = { betrag_nach = '(?i)gutschein' }    # Anteil, der nicht über die Bank läuft
haendler = { text = 'bei (.+)$', suche_in = "betreff", saeubern = true }
bezug = { text = 'Rechnung\s+(\S+)' }

[art.artikel]                           # optional: Artikelzeilen für die Beschreibung der Zahlung
zeile = '^(?P<name>.{3,}?)\s+(?P<betrag>[\d.,]+\s*€)$'
ausser = '(?i)summe|versand'

[bank]                                  # Bankseite
namen = ["kaufhaus muster"]             # so steht der Anbieter in Buchungen (mind. 3 Zeichen); Vorgabe: name
kennung = '(?<![A-Z0-9])K\d{6}(?!\d)'   # so sieht die Kennung im Verwendungszweck aus (ganzer Treffer)
glob = "*K[0-9][0-9][0-9][0-9][0-9][0-9]*"   # Grobfilter (SQLite-GLOB), spart das Lesen aller Buchungen
ohne_leerraum = false                   # true: auch ohne Leerraum suchen (Bank bricht die Nummer um)
alle_mails = false                      # true: Kennung in Mails aller Absender suchen
haendler = 'Einkauf bei (?P<haendler>[^,]+)'   # optional: Händler, wie ihn die Buchung nennt
haendler_noetig = false                 # true: ohne Kennung zählt nur eine Buchung mit dem Händler der Mail
tage_vor = 3                            # Zeitfenster um das Maildatum (Vorgabe 3 Tage davor, 45 danach)
tage_nach = 45
```

Ausdrücke sind Python-`re`; Groß-/Kleinschreibung nur mit `(?i)` egal. In TOML stehen sie am besten in einfachen
Anführungszeichen (`'…'`), dann braucht `\` keine Verdopplung. Höchstens 500 Zeichen je Ausdruck.

## Rollen

| Rolle | Wirkung |
| --- | --- |
| `ausgabe` | Aus der Mail entsteht eine erwartete Zahlung (Abgang). Mails mit derselben Kennung gehören zu ihr. |
| `erstattung` | Erwarteter Eingang. `bezug` verweist auf die Kennung der ursprünglichen Zahlung; nennt die Mail keinen Händler, gilt deren Händler. |
| `storno` | Schließt die noch offene erwartete Zahlung mit derselben Kennung. |

## Bausteine

Beträge (`gesamt`, `guthaben`):

| Baustein | Bedeutung |
| --- | --- |
| `betrag_nach = '…'` | Betrag in der Zeile hinter dem Treffer, sonst in der Zeile darunter. Die erste Zeile mit Betrag gilt. |
| `betrag_summe_nach = '…'` | Summe der Beträge, die in einer Zeile hinter dem (letzten) Treffer stehen. |
| `wenn = '…', dann = "gesamt"` | Trifft der Ausdruck im Text zu, der ganze Betrag, sonst 0 (z. B. „auf Ihr Guthaben gutgeschrieben“). |
| `fest = 0` | Fester Betrag in Cent. |

Texte (`haendler`, `bezug`):

| Baustein | Bedeutung |
| --- | --- |
| `text = '…'` | Gruppe 1 (oder `(?P<wert>…)`) des ersten Treffers; `suche_in = "betreff"` sucht im Betreff, `saeubern = true` entfernt Anführungszeichen am Rand. |
| `kennung = true` | Die Kennung der Mail. |
| `fest = "…"` | Fester Text. |

Statt eines Bausteins ist eine Liste erlaubt; der erste mit Ergebnis gilt. Beträge schreibt die Mail deutsch
(`1.234,56 €`, `EUR 9,99`); die Umrechnung in Cent macht Kontor, nicht der Ausdruck.

## Wie zugeordnet wird

1. **Kennung in der Buchung:** Steht die Kennung der erwarteten Zahlung (oder ihr Bezug) im Verwendungszweck oder
   beim Empfänger, wird zugeordnet.
2. **Betrag und Name:** Gibt es genau eine freie Buchung mit dem Betrag im Zeitfenster, in der einer der
   `bank.namen` oder der Händler steht, wird zugeordnet.
   Mit `haendler_noetig = true` (PayPal: der Anbieter steht in jeder seiner Buchungen) zählt statt `bank.namen`
   nur der **Händler der Mail, in Teilen**: Es genügt ein aussagekräftiges Wort des Namens im Text der Buchung
   (Allerweltswörter wie „Shop“ oder „GmbH“ zählen nicht); gekürzte, zusammengeschriebene Namen der Bank
   („MEDIAMARKTSATU“) werden über `bank.haendler` erkannt. Andere Buchungen gleichen Betrags ohne den Händler
   stören dann nicht; zwei passende Buchungen bleiben zur Bestätigung von Hand.
3. **Von Hand:** Alles andere erscheint als Vorschlag unter „Was kommt noch?“.

Mit `KONTOR_MAIL_BESTELLNUMMER=1` gilt zusätzlich, unabhängig von erwarteten Zahlungen: Jede Mail, in der eine
Kennung nach `bank.kennung` steht, hängt als Dokument an jeder Buchung mit derselben Kennung.

