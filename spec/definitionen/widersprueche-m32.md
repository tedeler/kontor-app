# Widersprüche aus dem Lauf der M32-Abnahmetests gegen die Anwendung (2026-11-22)

Vom Implementierungs-Thread als Text gemeldet. Nur ein Test-Thread löst sie (Test oder Spezifikation anpassen,
Entscheidung `E-…` anlegen).

## W-022 Mail-Gruppen: Mail nach dem Datum der App-Uhr

- Tests: `tests/app/m32/test_m32_mail.py::test_gruppieren_aelteste`, `::test_gruppieren_neueste_und_filter`
  (KeyError „Bestellung 306-1111111-2222222“).
- Die Mail „E“ ist am 2024-06-06 empfangen; `m20.app` setzt die App-Uhr auf `heute = 2024-06-05`.
- Spezifikation `mail.md` 6.2 Schritt 3: im Mock-Modus vorher `setze_heute` mit dem Datum der App-Uhr; das
  Mock-Mail-Plugin liefert nur Nachrichten bis zu diesem Tag (`python-api.md`, Mock-Mail-Plugin). Die Mail
  wird also noch nicht abgerufen und fehlt in der Liste.
- Vorschlag: `heute` des Tests auf 2024-06-06 oder später setzen bzw. die Mail früher datieren.

## W-023 Bilder fremder Server: „Giro“ zweimal auf oberster Ebene

- Test: `tests/app/m32/test_m32_mail.py::test_bilder_anzahl`.
- `_mail_dokument` legt bei jedem Aufruf `Giro` (und `Einkauf`) neu an; der Test ruft es zweimal in derselben
  App auf. Seit D-218 (Kontonamen je Ebene eindeutig, `sammel3.md` 1, in M32 selbst übernommen) lehnt die App
  das zweite Anlegen mit 409 `konto_existiert` ab.
- Vorschlag: Konten in `_mail_dokument` nur einmal anlegen (oder vorhandene wiederverwenden).

## W-024 `bilder` mit ungültigem Wert: 422 nicht in `openapi.yaml`

- Test: `tests/app/m32/test_m32_mail.py::test_bilder_nur_auf_wunsch` (letzte Zeile).
- E-300 legt fest: anderer Wert von `bilder` → 422 `validierung`. `openapi.yaml` nennt für
  `GET /api/dokumente/{dokument_id}/mail/html` aber nur 200, 404, 409; die Testhilfe lehnt die 422-Antwort der
  App deshalb als „nicht spezifiziert“ ab.
- Vorschlag: 422 (`Fehler`) bei der Operation in `openapi.yaml` ergänzen.

## W-025 „Anzeigen im Konto“: `empfaenger_id` in der Adresse gegen `filter=` (M30)

- Test: `tests/app/m32/test_m32_oberflaeche.py::test_empfaenger_anzeigen_im_konto` (wartet auf
  `empfaenger_id=<id>` in der Adresse des Kontoblatts).
- Definition 4 (D-220, `oberflaeche.md` 41): `em-im-konto` öffnet `/konten/<id>?empfaenger_id=<id>`.
- `oberflaeche.md` 39.2 (M30): Der Filter steht in der Adresse als `filter=…`; frühere Einzelparameter werden
  beim Öffnen in den Ausdruck übernommen (die M8-Tests `test_filter` verlangen nach der Übernahme `filter=` in
  der Adresse). Die App öffnet daher zwar mit `?empfaenger_id=<id>`, schreibt die Adresse danach aber in
  `filter=empf == "<Name>"` um (oder gleichwertig).
- Die beiden Stellen widersprechen sich, sobald man die Adresse nach dem Laden prüft. Vorschlag: im M32-Test
  den Filter des Kontoblatts prüfen (Ausdruck nennt den Empfänger, nur dessen Buchungen sichtbar) statt des
  Parameters, oder in 39.2 `empfaenger_id` als bleibenden Parameter ausnehmen (dann aber auch die M8-Tests).

## W-026 Mail-Blatt im Browser: Mails außerhalb des Erstabrufs

- Tests: `tests/app/m32/test_m32_oberflaeche.py::test_mail_suche_in_der_adresse`, `::test_mail_handy_ohne_vorwahl`,
  `::test_mail_zuordnen_knopf` (KeyError beim Nachschlagen nach Betreff in `_mail_server`).
- Die Mails sind vom 2024-06-01/02; die Browser-Server laufen mit `m8.HEUTE = 2024-12-31`. Nach `mail.md` 6.2
  Schritt 2 ist `seit` beim ersten Abruf `jetzt − mail_erstabruf_tage` (Vorgabe 30) – Mails vor dem 2024-12-01
  werden nicht gespiegelt.
- Vorschlag: Mails im Dezember 2024 datieren oder `mail_erstabruf_tage` für den Server erhöhen.
