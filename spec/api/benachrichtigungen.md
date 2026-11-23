# Benachrichtigungen per ntfy und TAN-Erinnerungen – Meilenstein 6

Verbindlich für Implementierung und Tests. Umsetzung von K 3
(„Benachrichtigungen: ntfy“), K 6 Schritte 2 und 4 (Push mit Link zur
TAN-Seite, Erinnerungen in Abständen) und T 17 (jeder Auslöser genau eine
Nachricht an eine ntfy-Attrappe, keine Nachrichtenflut). Ergänzt
`synchronisation.md` (11, 18), `python-api.md` (13), `plugins.md` (9) und
`openapi.yaml` (Tag `benachrichtigungen`).
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

## 1. Überblick

Die interne Benachrichtigungsliste aus M2 (`synchronisation.md` 11) bleibt
die einzige Quelle: Jede Benachrichtigung entsteht dort genau einmal nach
den Entprellregeln ihrer Art. M6 **stellt** jede neue Benachrichtigung
zusätzlich über ein austauschbares Benachrichtigungs-Plugin zu – genau eine
Push-Nachricht je Benachrichtigung. Wiederholt wird nur nach einem
Fehlschlag. Eine Flut ist damit ausgeschlossen, solange die Entprellung der
Arten greift.

## 2. Plugins und Auswahl

| `benachrichtigung_plugin` | Wirkung | erlaubt |
| --- | --- | --- |
| `keins` | keine Zustellung (`zustellung = "keine"`) | Mock- und Echtmodus |
| `mock` | Zustellung in eine Liste im Arbeitsspeicher, keine Verbindung | nur Mock-Modus |
| `ntfy` | HTTP-POST an einen ntfy-Server (3) | Mock- und Echtmodus (E-119) |

Vorgabe (None): `mock` im Mock-Modus, `keins` im Echtmodus. Ohne
Konfiguration ändert sich also für Tests früherer Meilensteine nichts außer
den neuen, optionalen Feldern (4.1). Im Mock-Modus beginnt der Titel jeder
Push-Nachricht mit `[Mock] ` (4.2), damit Mock-Meldungen auf dem Handy
erkennbar sind.

Schnittstelle (`python-api.md` 13.3):

```python
# kontor.plugins.benachrichtigung
@dataclass(frozen=True)
class PushNachricht:
    benachrichtigung_id: int
    titel: str
    text: str
    link: str | None          # absolute URL oder None
    prioritaet: int           # 1–5 (ntfy: 1 min … 5 max)
    tags: tuple[str, ...]
    schluessel: str

class BenachrichtigungsPlugin(abc.ABC):
    name: ClassVar[str]        # "mock" | "ntfy"
    ist_mock: ClassVar[bool]
    @abc.abstractmethod
    def senden(self, nachricht: PushNachricht) -> None: ...
    def schliessen(self) -> None: ...      # nicht abstrakt; Vorgabe: tut nichts
```

- `senden` liefert nichts bei Erfolg und wirft sonst `BenachrichtigungFehler`
  (Code `benachrichtigung_fehler`, `details.status` = HTTP-Status oder
  null). Öffentliche Methoden eines Plugins sind genau `senden` und
  `schliessen`.
- `kontor.plugins.mock_benachrichtigung.MockBenachrichtigungsPlugin()`:
  `name = "mock"`, `ist_mock = True`, Attribut `gesendet: list[PushNachricht]`
  in Zustellreihenfolge; baut nie eine Verbindung auf; `senden` gelingt immer.
- `kontor.plugins.ntfy.NtfyPlugin(config, *, token_quelle=None)`:
  `name = "ntfy"`, `ist_mock = False`; `token_quelle()` liefert das
  ntfy-Token oder None (bei jedem Senden aufgerufen, nicht beim Erzeugen).
  Das Erzeugen baut keine Verbindung auf.
- `kontor.plugins.erzeuge_benachrichtigungs_plugin(config, *, token_quelle=None)`
  → Plugin nach der Tabelle oder `None` bei `keins`. Die App übergibt als
  `token_quelle` das Geheimnis `ntfy_token` (`geheimnisse.md` 4).

## 3. ntfy-Protokoll

Ein Senden ist genau eine HTTP-Anfrage:

- `POST` an `ntfy_url` ohne abschließendes `/`, gefolgt von `/` (JSON-Veröffentlichung
  an der Wurzel, z. B. `https://ntfy.sh/`).
- Kopf `Content-Type: application/json`; `Authorization: Bearer <token>`
  genau dann, wenn `token_quelle()` einen nicht leeren Wert liefert; keine
  weiteren Zugangsdaten.
- Körper (UTF-8-JSON) mit **genau** diesen Schlüsseln:
  `topic` (= `ntfy_topic`), `title`, `message`, `priority`, `tags` (Liste) und
  – nur wenn `link` nicht None ist – `click`.
- Erfolg: Status 200–299 (Körper wird nicht ausgewertet). Jeder andere
  Status, Verbindungsfehler und Zeitüberschreitung nach
  `ntfy_timeout_sekunden` → `BenachrichtigungFehler`. Umleitungen werden
  nicht verfolgt.
- TLS nach `geheimnisse.md` 7.

## 4. Zustellung

### 4.1 Neue Felder der Benachrichtigung

`Benachrichtigung` (`synchronisation.md` 11) erhält drei Felder (im Schema
optional, in den M6-Tests Pflicht):

| Feld | Typ | Regeln |
| --- | --- | --- |
| `zustellung` | `"keine"` \| `"ausstehend"` \| `"zugestellt"` \| `"aufgegeben"` | bei Entstehung `keine` (Plugin `keins`) bzw. `ausstehend` |
| `zustellversuche` | int | Anzahl der Aufrufe von `senden` für diese Benachrichtigung |
| `zugestellt_am` | date-time \| null | App-Uhr beim erfolgreichen Senden |

`zustellung = "keine"` bleibt für immer so (auch nach einem späteren
Wechsel des Plugins). Benachrichtigungen, die vor M6 entstanden sind, gelten
als `keine` mit `zustellversuche = 0`.

### 4.2 Push-Nachricht

| Feld | Wert |
| --- | --- |
| `benachrichtigung_id` | `id` |
| `titel` | `titel`, im Mock-Modus mit vorangestelltem `[Mock] ` |
| `text` | `text` |
| `link` | `oeffentliche_url` ohne abschließendes `/` + `link`, wenn beide gesetzt sind; sonst None |
| `prioritaet` | Tabelle 4.4 |
| `tags` | `(art,)` |
| `schluessel` | `schluessel` |

### 4.3 Ablauf

1. **Erster Versuch sofort:** Unmittelbar nach dem Schreiben einer neuen
   Benachrichtigung (`ausstehend`) ruft die App `senden` auf – in derselben
   Anfrage bzw. demselben Planer-Takt, bevor die Antwort zurückgeht.
2. Erfolg → `zugestellt`, `zugestellt_am` = jetzt.
3. Fehlschlag (jede Ausnahme) → `zustellversuche` + 1; ist
   `zustellversuche ≥ zustellung_max_versuche` → `aufgegeben`, sonst bleibt
   sie `ausstehend` mit *nächstem Versuch* = jetzt +
   `zustellung_wiederholung_minuten`. Ein Fehlschlag ändert nichts an der
   auslösenden Operation (kein 5xx, kein Abbruch eines Laufs).
4. **Wiederholung:** Jeder Planer-Takt (`synchronisation.md` 18.2 Schritt 6)
   versucht alle `ausstehend`en Benachrichtigungen, deren nächster Versuch ≤
   jetzt ist, nach `id` aufsteigend.
   `POST /api/benachrichtigungen/zustellen` versucht alle `ausstehend`en
   sofort (ohne Rücksicht auf den nächsten Versuch) und antwortet 200 mit
   `{"versucht": n, "zugestellt": m}`.
5. Höchstens ein Zustellvorgang gleichzeitig je App; eine Benachrichtigung
   wird nie zweimal erfolgreich gesendet.
6. `gelesen` und Zustellung sind unabhängig.

`GET /api/benachrichtigungen/zustellung` → `ZustellStatus {plugin,
ausstehend, aufgegeben, zugestellt, letzter_fehler}` mit `plugin` ∈ {`keins`,
`mock`, `ntfy`}, Anzahlen je Zustand und `letzter_fehler` = `{code, meldung,
zeitpunkt}` des letzten Fehlschlags oder null. Im Mock-Modus liefert
`GET /api/mock/zustellungen` die Liste `MockBenachrichtigungsPlugin.gesendet`
als JSON (`PushNachricht`, Tupel als Liste), bei anderem Plugin `[]`; im
Echtmodus 409 `nur_mock_modus`.

### 4.4 Prioritäten

| `art` | `prioritaet` |
| --- | --- |
| `tan_erforderlich`, `tan_erinnerung`, `mail_token_abgelaufen`, `mail_token_widerrufen` | 4 |
| `mail_token_laeuft_ab` und alle übrigen Arten (`sync_fehler`, `tan_abgelaufen`, `split_abweichung`, `konto_fehlt`, `neuer_empfaenger`, `wiederkehrend_betrag`, `wiederkehrend_ausbleibend`, `mail_fehler`) | 3 |

### 4.5 Inhalt

Titel und Text sind deutsch und nicht leer (Inhalt sonst frei) und enthalten
nie ein Geheimnis (`geheimnisse.md` 6). Die TAN-Anforderung darf den
Anweisungstext der Bank (`challenge`) nennen, nie die TAN, die PIN oder das
Bild.

## 5. TAN-Erinnerungen (K 6 Schritt 4)

- Konfiguration: `tan_erinnerung_minuten` (Abstand *I*, Vorgabe 5; 0 = keine
  Erinnerungen) und `tan_erinnerung_anzahl` (Höchstzahl *N*, Vorgabe 3).
- Jeder Planer-Takt prüft nach den TAN-Abläufen (`synchronisation.md` 7.4)
  jede **offene** TAN-Anforderung `T` mit `erstellt_am = E`: Sei
  `k = ⌊(jetzt − E) / I⌋` (ganze Vielfache von *I*), `n = min(k, N)` und `m`
  die Nummer der zuletzt für `T` erzeugten Erinnerung (anfangs 0). Ist
  `n ≥ 1`, `n > m` und `jetzt ≤ gueltig_bis`, entsteht genau eine
  Benachrichtigung `art = "tan_erinnerung"`, `schluessel =
  "tan_erinnerung:<T.id>:<n>"`, `link = "/tan/<T.id>"`, und `m` wird `n`.
  Ausgelassene Nummern (später Takt) werden nicht nachgeholt.
- Beantwortete, abgebrochene und abgelaufene Anforderungen erhalten keine
  Erinnerungen mehr. Die Benachrichtigung `tan_abgelaufen` (M2) wird wie jede
  andere zugestellt.
- Die erste Push-Nachricht ist die Benachrichtigung `tan_erforderlich` aus
  M2 (K 6 Schritt 2) mit `link = "/tan/<id>"`; mit `oeffentliche_url` wird
  daraus der absolute Link zur TAN-Seite (Seite selbst: M8).
- `m` ist Betriebszustand (nicht gesichert, nicht protokolliert).

## 6. Neue Benachrichtigungsarten in M6

| `art` | Schlüssel | Link | Regeln |
| --- | --- | --- | --- |
| `tan_erinnerung` | `tan_erinnerung:<tan_id>:<n>` | `/tan/<tan_id>` | 5 |
| `mail_token_laeuft_ab` | `mail_token_laeuft_ab:<postfach_id>:<anmeldung_nr>` | `/mail/postfaecher/<postfach_id>` | `mail.md` 5.3 |
| `mail_token_abgelaufen` | `mail_token_abgelaufen:<postfach_id>:<anmeldung_nr>` | wie oben | `mail.md` 5.3 |
| `mail_token_widerrufen` | `mail_token_widerrufen:<postfach_id>:<anmeldung_nr>` | wie oben | `mail.md` 5.3 |
| `mail_fehler` | `mail_fehler:<postfach_id>:<code>` | wie oben | `mail.md` 6.3 |

Die Arten werden an die Aufzählung `Benachrichtigung.art` angehängt (E-029).

## 7. Attrappe für Tests (`tests/hilfen/ntfy_attrappe.py`)

Lokaler HTTP-Server auf `127.0.0.1` (optional mit TLS und eigenem
Zertifikat, `tests/hilfen/tls.py`). Er zeichnet jede Anfrage auf (Methode,
Pfad, Köpfe, Körper) und antwortet nach einer einstellbaren Folge von
Statuscodes (Vorgabe 200), optional verzögert; ist ein erwartetes Token
gesetzt, antwortet er ohne passenden `Authorization`-Kopf mit 401. Die App
erreicht ihn nur über `ntfy_url` (E-028).

## 8. Test-Benachrichtigung (ab M8, W-005, E-138)

Für den Knopf „Test-Benachrichtigung senden“ der Oberfläche (Einstellungen →
Benachrichtigungen, `oberflaeche.md` 13.2). Rückwärtskompatibel (E-029):
Eine neue Operation, keine Änderung bestehender Schemas.

`POST /api/benachrichtigungen/test` – ohne Anfragekörper (ein mitgesandter
Körper wird nicht ausgewertet). Geschützt wie jeder andere Endpunkt
(`sicherheit.md` 3.2, mit CSRF-Kopf 4.6).

| Plugin (`benachrichtigung_plugin`) | Wirkung | Antwort |
| --- | --- | --- |
| `keins` | nichts | 409 `kein_benachrichtigungs_plugin`, `details = {}` |
| `mock` | **kein** Aufruf von `senden`; nichts wird übertragen | 200 `{plugin: "mock", zugestellt: true, gesendet: false, fehler: null}` |
| `ntfy` | genau **ein** Aufruf von `senden` mit der Test-Nachricht (unten), ohne Wiederholung | Erfolg: 200 `{plugin: "ntfy", zugestellt: true, gesendet: true, fehler: null}`; `BenachrichtigungFehler`: 200 `{plugin: "ntfy", zugestellt: false, gesendet: true, fehler: {code: "benachrichtigung_fehler", meldung, status}}` mit `status` = `details.status` (HTTP-Status oder null bei Verbindungsfehler/Zeitüberschreitung) |

Test-Nachricht (`PushNachricht`, 2):

| Feld | Wert |
| --- | --- |
| `benachrichtigung_id` | `0` (keine Benachrichtigung der Liste) |
| `titel` | `Kontor: Test-Benachrichtigung`, im Mock-Modus mit vorangestelltem `[Mock] ` (wie 4.2) |
| `text` | deutsch, nicht leer, ohne Geheimnis (Inhalt sonst frei) |
| `link` | `oeffentliche_url` ohne abschließendes `/` + `/einstellungen`, wenn `oeffentliche_url` gesetzt ist; sonst None |
| `prioritaet` | 3 |
| `tags` | `("test",)` |
| `schluessel` | `test:` + App-Uhr im Format `YYYY-MM-DDTHH:MM:SSZ` |

Für `ntfy` ergibt das nach 3 genau eine HTTP-Anfrage mit den Schlüsseln
`topic`, `title`, `message`, `priority` (3), `tags` (`["test"]`) und – nur
mit `oeffentliche_url` – `click`; `Authorization` nach 3 (Geheimnis
`ntfy_token`).

Was die Test-Benachrichtigung **nicht** tut (geprüft):

- Sie erzeugt keine Benachrichtigung (`GET /api/benachrichtigungen`
  unverändert), ändert keine Zustellung, Zählung oder `letzter_fehler` in
  `GET /api/benachrichtigungen/zustellung` und keinen Eintrag in
  `GET /api/mock/zustellungen` (dort stehen nur Nachrichten zu
  Benachrichtigungen der Liste, eine je Benachrichtigung, T 17).
- Sie ist kein fachlicher Zustand: keine Änderung im Protokoll
  (`protokoll.md` 4), nicht Teil der Sicherung, kein Rückgängig.
- Ein Fehlschlag führt nie zu 5xx und wird nicht wiederholt; die Meldung
  enthält kein Geheimnis (`geheimnisse.md` 6), insbesondere nicht das
  ntfy-Token.

## 9. Neue Benachrichtigungsart in M20 (E-216)

| `art` | Schlüssel | Link | Regeln |
| --- | --- | --- | --- |
| `erwartung_ueberfaellig` | `erwartung_ueberfaellig:<erwartung_id>` | `/erwartet?id=<erwartung_id>` | `erwartungen.md` 4.2: je Erwartung höchstens einmal überhaupt (auch nach dem Lesen nicht erneut); Titel „Zahlung nicht abgebucht“ (Ausgabe) bzw. „Erstattung überfällig“ (Eingang); Priorität 3 wie die übrigen Arten (4.4) |

Die Art wird an die Aufzählung `Benachrichtigung.art` angehängt (E-029).
