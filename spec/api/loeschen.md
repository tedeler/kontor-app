# Konten und Kategorien löschen – Meilenstein 3

Verbindlich für Implementierung und Tests. Ergänzt `datenmodell.md` 2
und 13, `protokoll.md` 4.1, `buchhaltungspflege.md` (Abstimmungen,
Standardkategorie) und `openapi.yaml` (Operation
`kontoLoeschenMitBuchungen`). Entscheidungen: E-060 bis E-064.
Kategorien sind Konten (K 4); alles hier gilt für Konten jeder Art.

Das bisherige `DELETE /api/konten/{konto_id}` bleibt unverändert (M1, E-029):
Es löscht nur unbenutzte Konten und antwortet sonst mit 409
`konto_in_verwendung`. Ein benutztes Konto wird über die hier beschriebene
Operation gelöscht. Die Oberfläche fragt dabei, wie mit den Buchungen
umgegangen wird (Abschnitt 6).

War K einem Bankkonto zugeordnet, legt die Synchronisation es danach nicht
still neu an, sondern fragt (`synchronisation.md` 16, E-080).

## 1. Begriffe

- **K**: das zu löschende Konto.
- **Betroffene Buchungen** `B(K)`: alle Buchungen mit mindestens einem Split
  auf K. Splits auf Unterkonten von K zählen nicht.
- **Gesperrte Buchungen**: betroffene Buchungen, die gesperrt sind, also
  den Status `abgeglichen` haben oder `abgestimmt` sind
  (`buchhaltungspflege.md` 1.3). Maßgeblich ist der Zustand vor der
  Operation.
- **Zielkonto Z** (nur bei den Varianten mit Umbuchung):
  - `elternkonto`: das Elternkonto von K (`K.eltern_id`). Es hat dieselbe
    Klasse wie K (`datenmodell.md` 2).
  - `unkategorisiert`: das technische Konto „Unkategorisiert“
    (`extern_id = "kontor:unkategorisiert"`, `synchronisation.md` 4.2).
    Fehlt es, wird es angelegt, ebenso wie bei der Synchronisation.
- **Konfliktbuchung**: eine betroffene Buchung, bei der nach dem Umbuchen
  *alle* Splits auf Z buchen. Ihre Splits summieren sich dann zu 0 auf
  demselben Konto, die Buchung bewirkt also nichts mehr. Beispiele:
  - Umbuchung Girokonto → Sparkonto, das Sparkonto wurde früher schon nach
    „Unkategorisiert“ gelöscht, jetzt wird das Girokonto ebenfalls nach
    „Unkategorisiert“ gelöscht. Quelle und Ziel sind dann beide
    „Unkategorisiert“.
  - Buchung zwischen einem Unterkonto und seinem Elternkonto, das Unterkonto
    wird mit `elternkonto` gelöscht.

## 2. Anfrage

`POST /api/konten/{konto_id}/loeschen` mit Körper `KontoLoeschen`:

| Feld | Typ | Pflicht | Bedeutung |
| --- | --- | --- | --- |
| `buchungen` | `"loeschen"` \| `"elternkonto"` \| `"unkategorisiert"` | ja | Umgang mit den betroffenen Buchungen (3) |
| `konflikte` | `"loeschen"` \| `"behalten"` | ja | Umgang mit Konfliktbuchungen (3.3); bei `buchungen = "loeschen"` ohne Wirkung, aber trotzdem Pflicht |
| `gesperrte_einbeziehen` | bool | nein (false) | ausdrückliche Bestätigung, dass auch gesperrte Buchungen gelöscht oder umgebucht werden dürfen |
| `trocken` | bool | nein (false) | Probelauf: liefert das Ergebnis, ändert nichts |

Die Felder `buchungen` und `konflikte` haben bewusst keine Vorgabe. Die
Entscheidung muss immer ausdrücklich getroffen werden (E-061).

**Prüfreihenfolge** (die erste zutreffende Regel bestimmt die Antwort,
nichts wird geändert):

1. Körper ungültig (fehlendes Pflichtfeld, unbekannter Wert, falscher Typ,
   unbekanntes Feld) → 422 `validierung`.
2. K existiert nicht → 404 `nicht_gefunden`.
3. `buchungen = "elternkonto"` und K ist ein Wurzelkonto → 422
   `kein_elternkonto`.
4. `buchungen = "unkategorisiert"` und K ist selbst das Konto
   „Unkategorisiert“ → 422 `ziel_ungueltig`.
5. Kein Probelauf, `gesperrte_einbeziehen = false` und es gibt gesperrte
   Buchungen → 409 `buchung_gesperrt` mit `details = {"buchung_ids": [...]}`
   (alle gesperrten betroffenen Buchungen, aufsteigend).

## 3. Wirkung

Die Operation ist atomar: Entweder gelten alle folgenden Schritte oder
keiner.

### 3.1 Unterkonten

Alle direkten Unterkonten von K erhalten `eltern_id = K.eltern_id`. Sie
rücken also eine Ebene nach oben, ein Unterkonto eines Wurzelkontos wird
selbst Wurzelkonto. Das gilt bei jeder Variante. Unterkonten werden nie
mitgelöscht (E-063).

### 3.2 Buchungen

**`loeschen`:** Alle betroffenen Buchungen werden gelöscht, vollständig mit
allen Splits, auch denen auf anderen Konten. Offene Dublettenverdachte, in
denen eine dieser Buchungen vorkommt, werden gelöscht wie beim einzelnen
Löschen (`datenmodell.md` 9).

**`elternkonto` und `unkategorisiert`:** Jede betroffene Buchung wird so
behandelt:

1. Jeder Split auf K bucht künftig auf Z. Betrag, Memo und Split-`id`
   bleiben.
2. Ist die Buchung jetzt eine Konfliktbuchung, gilt 3.3. Sonst weiter mit 3.
3. **Zusammenfassen:** Buchen danach mindestens zwei Splits der Buchung mit
   `abstimmung_id = null` auf Z, werden diese zu einem Split
   zusammengefasst:
   - Position und `id` vom ersten dieser Splits (Reihenfolge der Buchung),
   - `betrag` = Summe der Beträge,
   - `memo` = die nicht leeren Memos dieser Splits in Reihenfolge, ohne
     exakte Wiederholungen, verbunden mit `" / "` (alle leer → `""`).

   Die übrigen dieser Splits entfallen. Abgestimmte Splits auf Z (aus einer
   Abstimmung von Z) werden nie zusammengefasst, damit der abgestimmte
   Betrag gleich bleibt. Splits auf anderen Konten bleiben unverändert und
   behalten ihre Reihenfolge. Ein zusammengefasster Split
   mit Betrag 0 bleibt bestehen (`datenmodell.md` 3).
4. `vorschlag` wird null (E-064). Status, Datum, Empfänger,
   Verwendungszweck, Tags und `extern_ids` bleiben.

Beispiel: Die Kategorie „Drogerie“ ist ein Unterkonto von „Haushalt“. Die
Buchung Girokonto `-1000`, Haushalt `+600` „Putzmittel“, Drogerie `+400`
„Seife“ wird beim Löschen von „Drogerie“ mit `elternkonto` zu Girokonto
`-1000`, Haushalt `+1000` „Putzmittel / Seife“. Damit ist sie
kategorisierbar mit `kategorie_id` = Haushalt.

### 3.3 Konfliktbuchungen

- **`konflikte = "loeschen"`:** Die Buchung wird gelöscht (mit offenen
  Dublettenverdachten wie in 3.2).
- **`konflikte = "behalten"`:** Die Buchung bleibt. Alle ihre Splits buchen
  auf Z, ohne Zusammenfassen: Anzahl, Reihenfolge, `id`, Beträge und Memos
  bleiben. `vorschlag` wird null. Damit bleiben Datum, Empfänger und
  Verwendungszweck erhalten und die Buchung kann später neu zugeordnet
  werden. Auf Z sind solche Buchungen daran zu erkennen, dass jeder Split
  auf Z bucht.

Bei `buchungen = "loeschen"` gibt es keine Konfliktbuchungen.

### 3.4 Regeln

Regeln, die auf K verweisen (`kategorie_id = K` oder eine Bedingung
`konto_id` mit `wert = K`, `kategorisierung.md` 1.2):

- bei `elternkonto`: Jeder Verweis auf K wird durch Z ersetzt. Die Regel
  bleibt sonst unverändert (Name, Priorität, aktiv, Reihenfolge der
  Bedingungen).
- bei `loeschen` und `unkategorisiert`: Die Regel wird gelöscht, mit
  derselben Wirkung wie `DELETE /api/regeln/{id}` (`regel_id` in Vorschlägen
  wird null).

### 3.5 Standardkategorien von Empfängern

Empfänger mit `standardkategorie_id = K` (`buchhaltungspflege.md` 2):

- bei `elternkonto`: `standardkategorie_id = Z` (Z ist wie K eine
  Kategorie),
- bei `loeschen` und `unkategorisiert`: `standardkategorie_id = null`.

### 3.6 Abstimmungen

Alle Abstimmungen mit `konto_id = K` (`buchhaltungspflege.md` 5) werden
gelöscht, bei jeder Variante. Splits mit der `abstimmung_id` einer dieser
Abstimmungen erhalten null, wie beim Aufheben (5.3), aber ohne die
Einschränkung auf die letzte Abstimmung. Das geschieht vor dem Umbuchen.
Die betroffenen Buchungen waren gesperrt und sind daher nur mit
`gesperrte_einbeziehen = true` erreichbar. Abstimmungen anderer Konten
bleiben, ebenso ihre Splitmarken, auch wenn die Buchung umgebucht wird.

### 3.7 Konto

Zum Schluss wird K gelöscht. Seine ID wird nie wiederverwendet
(`datenmodell.md` 1). Vorschläge anderer Buchungen mit `vorher_konto_id = K`
bleiben unverändert. Beim Ablehnen greift dann die bestehende Regel
(„existiert das Konto nicht mehr: Unkategorisiert“, `kategorisierung.md` 5).

### 3.8 Änderungsprotokoll

Ein erfolgreicher Lauf ohne `trocken` erzeugt genau eine Änderung
(`protokoll.md` 4.1): `quelle = "manuell"`, `aktion =
"konto_loeschen_mit_buchungen"`, `gruppe = null`. Sie enthält die
Nettowirkung über alle Schritte: das gelöschte Konto, verschobene
Unterkonten, gelöschte und geänderte Buchungen, ein dabei angelegtes Konto
„Unkategorisiert“, Regeln, Empfänger, Abstimmungen und entfernte
Dublettenverdachte. Rückgängig (`protokoll.md` 6) stellt den Zustand vor
dem Löschen exakt wieder her: K mit derselben ID, Unterkontenzuordnung,
Buchungen mit Split-IDs, Vorschläge, Regeln, Standardkategorien,
Abstimmungen samt Splitmarken und Dublettenverdachte.

### 3.9 Folgerungen (getestet)

- Die Invarianten aus `datenmodell.md` 3 und T 3.1–3.4 gelten danach
  weiter. Insbesondere ist die Summe aller Kontensalden 0.
- Bei `elternkonto` und `unkategorisiert` gilt
  `saldo_neu(Z) = saldo_alt(Z) + saldo_alt(K)`, unabhängig von der
  Konfliktentscheidung. Alle anderen Konten behalten ihren Saldo, denn
  Konfliktbuchungen buchen nur auf K und Z.
- Bei `elternkonto` bleibt `saldo_gesamt` jedes Vorfahren von K gleich.
- Bei `loeschen` sinkt der Saldo jedes anderen Kontos genau um die Summe
  seiner Splits in den gelöschten Buchungen.

## 4. Antwort

200 mit `KontoLoeschErgebnis`. Ein Probelauf liefert dasselbe Ergebnis, das
der echte Lauf liefern würde. Dabei wird so gerechnet, als wäre
`gesperrte_einbeziehen = true`; ein Probelauf antwortet also nie mit 409.

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `konto_id` | int | K |
| `trocken` | bool | wie angefragt |
| `buchungen` | str | gewählte Variante |
| `konflikte` | str | gewählte Konfliktbehandlung |
| `ziel_konto_id` | int \| null | Z; null bei `loeschen` und im Probelauf, wenn „Unkategorisiert“ noch nicht existiert |
| `buchungen_betroffen` | Liste int | `B(K)` |
| `buchungen_geloescht` | Liste int | gelöschte Buchungen (Variante `loeschen` bzw. Konfliktbuchungen mit `konflikte = "loeschen"`) |
| `buchungen_umgebucht` | Liste int | betroffene Buchungen, die bestehen bleiben |
| `konfliktbuchungen` | Liste int | alle Konfliktbuchungen, gleich wie entschieden |
| `gesperrt` | Liste int | gesperrte betroffene Buchungen |
| `unterkonten` | Liste int | direkte Unterkonten, die eine Ebene nach oben gerückt sind |
| `regeln_geaendert` | Liste int | Regeln, deren Verweise ersetzt wurden |
| `regeln_geloescht` | Liste int | gelöschte Regeln |
| `empfaenger_geaendert` | Liste int | Empfänger, deren Standardkategorie geändert wurde |
| `abstimmungen_geloescht` | Liste int | gelöschte Abstimmungen von K |
| `aenderung_id` | int \| null | ID der Änderung (3.8); null im Probelauf |

Alle Listen aufsteigend, ohne Doppelte. Es gilt:
`buchungen_betroffen = buchungen_geloescht ∪ buchungen_umgebucht`
(disjunkt), `konfliktbuchungen ⊆ buchungen_betroffen`,
`gesperrt ⊆ buchungen_betroffen`.

## 5. Oberfläche (M8)

- Im Kontextmenü eines Kontos bzw. einer Kategorie gibt es „Löschen…“.
- Ein unbenutztes Konto wird nach einer einfachen Rückfrage gelöscht.
- Bei einem benutzten Konto erscheint ein Dialog mit:
  - den Zahlen aus einem Probelauf (betroffene Buchungen, Unterkonten,
    Regeln),
  - der Wahl „Buchungen löschen“ / „dem übergeordneten Konto zuschlagen“
    (bei Wurzelkonten deaktiviert) / „als unkategorisiert einstufen“,
    ohne Vorauswahl,
  - bei Konfliktbuchungen deren Liste und der Wahl „löschen“ / „behalten“,
  - bei gesperrten Buchungen (abgeglichen oder abgestimmt) einer eigenen
    Bestätigung.
- Erst nach ausdrücklicher Bestätigung wird ausgeführt. Danach lässt sich
  der Vorgang über das Änderungsprotokoll rückgängig machen (Undo).
- Die stabilen Merkmale (`data-testid`) legt die M8-Spezifikation fest.

## 6. Meilenstein 4: Split-Vorlagen

Ohne Vorlagen unverändert (E-029). Vorlagen, die auf K verweisen
(Teil-`kategorie_id = K` oder eine Bedingung `konto_id` mit `wert = K`,
`vorlagen.md` 1), werden wie Regeln in 3.4 behandelt (E-079):

- bei `elternkonto`: Jeder Verweis auf K wird durch Z ersetzt (Teile mit
  gleicher Kategorie werden **nicht** zusammengefasst; Name, Priorität,
  aktiv, Reihenfolge der Bedingungen und Teile, Beträge und Memos bleiben).
- bei `loeschen` und `unkategorisiert`: Die Vorlage wird gelöscht.

Die Antwort (`KontoLoeschErgebnis`) bleibt unverändert, sie erhält keine
Felder für Vorlagen (E-094); welche Vorlagen betroffen sind, ergibt sich aus
`GET /api/vorlagen` bzw. aus der Änderung im Protokoll. Ein Probelauf ändert
auch an Vorlagen nichts. Die Änderungen gehören zur Änderung
`konto_loeschen_mit_buchungen` und werden mit ihr rückgängig gemacht.

## 7. Meilenstein 5: Kredite

Ohne Kredite unverändert (E-029). Verweist ein Kredit auf K (`konto_id`,
`zahlungskonto_id` oder `zins_konto_id`, `kredite.md` 2.3), antwortet die
Operation nach Schritt 2 der Prüfreihenfolge (2) mit 409
`konto_in_verwendung` und `details = {"kredit_ids": [...]}` (aufsteigend),
auch im Probelauf; nichts wird geändert (E-110). Zuerst muss der Kredit
geändert oder gelöscht werden. Löscht die Operation eine Buchung, die einem
Kredit zugeordnet ist, entfällt die Zuordnung in derselben Änderung
(`kredite.md` 2.3).

## 8. Meilenstein 30: Verweise aus Ausdrücken

Verweist der Ausdruck einer Regel auf K (`konto == "…"` oder
`kategorie == "…"`, auch in Listen; `kategorisierung.md` 8.4), zählt das wie
ein Verweis nach 3.4:

- `DELETE /api/konten/{id}` → 409 `konto_in_verwendung`.
- bei `elternkonto`: Der Verweis wird durch Z ersetzt; der Ausdruck zeigt
  danach den Pfad von Z. Die Regel steht in `regeln_geaendert`.
- bei `loeschen` und `unkategorisiert`: Die Regel wird gelöscht
  (`regeln_geloescht`).
- `POST /api/kategorien/zusammenfuehren` (`alfbanco.md` 5): Der Verweis auf
  eine Quelle wird durch das Ziel ersetzt.

Hat eine Regel `kategorie_id = null`, entfällt für sie der Verweis über die
Kategorie; Tags sind keine Konten und bleiben unberührt.
