# Testumbau: Tests im Anwendungs-Repository

Stand 2026-11-23. Ausgangsstand der Messungen: kontor-app `667af00` (Version 0.46), kontor-tests `b6f94f1`.
Alle Zeiten auf 2 Kernen (`-n 2`); „Rechenzeit“ ist die Summe der Testdauern.

## Beschlossen

- kontor-tests wird aufgegeben. Spezifikation, Tests, Fixtures und Generator liegen in kontor-app.
- Neue Features: zuerst Core-Tests (eigener Commit vor dem Feature-Code), dann TDD. Muss ein Core-Test in der
  Schleife angepasst werden, wird das in `tests/core/AENDERUNGEN.md` dokumentiert.
- Zeitbudgets: Core-Tests unter 30 Sekunden; die Gesamttests laufen in parallelen CI-Jobs, jeder unter 5 Minuten.
  Vereinbart waren zwei Jobs (ohne Browser, mit Browser). Es sind vier geworden (eigene Tests, Gesamtsuite in zwei
  Teilen, Browser), weil die Runner von GitHub je Kern etwa halb so schnell sind wie die Messumgebung und der Job
  ohne Browser dort 7:15 min brauchte.
- Die Gesamttests laufen nur in der CI auf main, vor dem Release.

## Aufbau

| Pfad | Inhalt | läuft |
| --- | --- | --- |
| `spec/` | Spezifikation (Konzept, Testkonzept, `api/`, Meilensteine, Definitionen) | – |
| `tests/core/` | Core-Tests der Entwicklungsschleife, Regeln in `tests/core/README.md` | bei jeder Änderung, CI |
| `tests/` | eigene Tests je Feature; `test_browser*.py` tragen den Marker `browser` | CI |
| `gesamt-tests/` | gekürzte Fassung der früheren Abnahmetests (eigene `pytest.ini`, Fixtures, Generator) | CI |
| `legacy-tests/` | unveränderter Stand von kontor-tests, nur Referenz | nie |

Aufrufe:

```bash
python -m pytest tests/core                                  # Entwicklungsschleife
python -m pytest -n auto -m "not browser and not core" tests # eigene Tests ohne Browser
python -m pytest -n auto -m browser tests                    # eigene Browsertests
cd gesamt-tests && python -m pytest -n auto -m "not browser" # Gesamtsuite ohne Browser
cd gesamt-tests && python -m pytest -n auto -m browser       # Gesamtsuite mit Browser
cd gesamt-tests && python -m pytest -n auto --alle           # auch die abgewählten Tests
cd gesamt-tests && python -m pytest -n auto --teil 1/2       # ein Teil von mehreren gleich großen (CI)
```

## Messung

| Lauf | Tests | Dauer | Rechenzeit |
| --- | --- | --- | --- |
| vorher: legacy-tests, Volllauf | 4288 | 25:20 min | 2996 s |
| vorher: eigene Tests | 589 | 3:18 min | 377 s |
| **jetzt: Job ohne Browser** (Core 2, eigene 500, Gesamtsuite 2971) | 3473 | 6:35 min | etwa 790 s |
| **jetzt: Job mit Browser** (eigene 89, Gesamtsuite 191) | 280 | 4:16 min | etwa 475 s |

Die Zeilen „jetzt“ sind lokal gemessen und fassen die Tests ohne Browser in einem Lauf zusammen. Die Zeiten der
vier CI-Jobs stehen im Abschnitt „CI“.

## CI

`.github/workflows/release.yml`: bei jedem Push auf main vier parallele Jobs, danach (nur bei Grün) das Release.

Erster grüner Lauf (2026-11-23, Version 0.47), Dauer je Job einschließlich Einrichtung:

| Job | Inhalt | Tests | Dauer |
| --- | --- | --- | --- |
| `eigene` | `tests/core`, eigene Tests ohne Browser | 502 | 1:18 min |
| `gesamt-1` | Gesamtsuite ohne Browser, Teil 1 von 2 | 1516 | 3:15 min |
| `gesamt-2` | Gesamtsuite ohne Browser, Teil 2 von 2 | 1459 | 3:44 min |
| `browser` | eigene Browsertests, Gesamtsuite mit Browser | 280 | 3:51 min |

Bis alle Tests fertig waren, vergingen 3:51 min; mit dem Release danach 4:36 min.

- Im Browser-Job ist ein übersprungener Test ein Fehler (`KONTOR_TESTS_BROWSER_PFLICHT=1`), damit ein fehlender
  Browser nicht unbemerkt bleibt.
- 12 eigene Tests verlangen root und werden in der CI übersprungen (`test_https_skript_eigen.py`,
  `test_testinstanz_skript_eigen.py`); das war schon vor dem Umbau so.
- Wächst ein Job über 5 Minuten: zuerst kürzen oder abwählen; die Gesamtsuite lässt sich mit `--teil K/N` auch in
  mehr Teile schneiden.

### Wohin die Zeit ging

| Ursache | Anteil am Volllauf | Maßnahme |
| --- | --- | --- |
| Browser-, Leistungs- und Großdatentests (618 Tests) | 34 % | Browsertests ausgewählt (unten); `leistung` und `langsam` laufen nicht in der CI |
| Zufallstests mit 40 Beispielen | 22 % | Hypothesis-Profil `schnell` (10 Beispiele) ist die Vorgabe |
| Ein Thread mit Ereignisschleife je REST-Anfrage (Starlette `TestClient`) | etwa 13 % | eine gemeinsame Schleife je Testprozess (`tests/hilfen/api.py`, `tests/conftest.py`) |
| App-Aufbau je Test (etwa 0,1 s: 235 Routen, Schema) | etwa 12 % | unverändert; nur über weniger Tests zu senken |
| übrige Testarbeit | Rest | Auswahl (unten) |

Berichtigung zur ersten Fassung dieses Dokuments: Der App-Aufbau je Test ist mit rund 370 s über alle Tests sehr
wohl ein spürbarer Anteil, nur kein einzelner Engpass.

## Auswahl

`gesamt-tests/abgewaehlt.txt` nennt 998 Tests, die nur mit `--alle` laufen. Auswahlregel:

1. **Ohne Browser (697 abgewählt, 2971 bleiben):** Für jeden Test wurde gemessen, welche Zeilen und Verzweigungen
   von `src/kontor` er ausführt. Behalten wurden alle Tests unter 0,12 s, dann so lange der Test mit den meisten
   neuen Verzweigungen je Sekunde, bis alle 26 501 gemessenen Verzweigungen abgedeckt waren, und schließlich von
   jeder noch nicht vertretenen Testfunktion die schnellste Variante. Von 1720 Testfunktionen entfällt genau eine
   ganz (`m31/test_m31_lernmodell.py::test_lerndaten_laden_und_rueckgaengig`, 8 s); sonst entfallen nur weitere
   Parametervarianten.
2. **Mit Browser (301 abgewählt, 191 bleiben):** Gemessen wurden die ausgeführten JavaScript-Blöcke je Test. Die
   eigenen Browsertests bleiben vollständig; aus der Gesamtsuite bleiben die Tests, die darüber hinaus neue Blöcke
   ausführen (125), und bis zum Zeitbudget weitere Testfunktionen (schnellste zuerst). Alle 3890 gemessenen Blöcke
   bleiben abgedeckt; von 363 Testfunktionen bleiben 188.

Grenze der Methode: Abgedeckter Code ist nicht dasselbe wie geprüftes Verhalten. Ein abgewählter Test kann eine
Aussage prüfen, die kein verbleibender Test prüft, obwohl er denselben Code durchläuft. Die abgewählten Tests
bleiben deshalb im Verzeichnis und sind mit `--alle` jederzeit ausführbar. Die Liste gilt nach Knoten-ID: wird ein
Test umbenannt, läuft er wieder mit.

Nicht übernommen: `tests/_selbstpruefung` (Wegwerf-Referenz und Mutanten; nur in `legacy-tests`).

## Geänderte Tests gegenüber legacy-tests

Im Ausgangsstand schlugen 19 Tests der Abnahmesuite und 3 eigene fehl. Kein Anwendungscode wurde geändert.

| Test | Ursache | Änderung |
| --- | --- | --- |
| `m13/test_m13_oberflaeche` (2), `m8/test_m8_auslieferung` (1), `m8/test_m8_grundgeruest` (2), eigene `test_browser.py::test_ueber_fenster`, `test_versionierung_eigen.py::test_huelle_zeigt_version_in_der_navigation` | Auf einem Feature-Branch zeigt die App den Branch statt der Version; die Tests liefen nur auf main grün | Beide Suiten setzen den Branch für Tests außer Kraft (`_ohne_branch` bzw. `tests/conftest.py`) |
| `m8/test_m8_panels_mobil.py::test_wischen_links_setzt_kategorie_und_rueckgaengig` | D-290: Die Zeile zeigt die Kategorie sofort; das Attribut der Zeile ist kein Zeichen mehr dafür, dass neu geladen ist | wartet zusätzlich auf `data-ausstehend="0"` an `seite-konto`, bevor es mit den Zeilen weiterarbeitet |
| `test_buchungen.py::test_kategorie_setzen_fehler` | D-242: Bestandskonto ist als Ziel zulässig | erwartet `konto_ungueltig` für das eigene Konto, `kategorie_ungueltig` nur noch für Eigenkapital |
| `test_mehrfach.py::test_kategorie_ziel_ungueltig` (2 Varianten), `test_kategorie_pruefreihenfolge`, `test_mehrfach_kategorie_gegen_modell` | D-242 | Bestandskonten als ungültiges Ziel entfernt bzw. durch Eigenkapital ersetzt |
| `test_plugins.py::test_nur_lesende_oeffentliche_methoden` (2), `m6/test_m6_paket.py::test_oeffentliche_methoden` | D-243: Mail-Plugin hat `koepfe` und `inhalte` | erwartete Methodenmenge ergänzt |
| `m8/test_m8_seiten.py::test_seiten_im_mindestumfang` | Ohne Treffer zeigt „Regeln anwenden“ nur die Erfolgsmeldung, die ausgeliefert aus ist | Seite mit eingeschalteter Erfolgsmeldung |
| `m8/test_m8_split_dnd.py::test_umbuchung_auf_kategorie_ziehen_aendert_nichts` | D-242: Eine Umbuchung lässt sich jetzt zuordnen; die Aussage des Tests gilt nicht mehr | Test entfernt |
| `m8/test_m8_tastatur.py::test_alt_ziffern_und_schraegstrich`, `::test_suche_und_tastaturhilfe`, `m28/test_m28_kontoblatt.py::test_kuerzel_aktionen_und_vortasten` | D-292: `/` entfällt, die Hilfe liegt auf `h` | Suche über `w s`, Hilfe über `h` |
| `m28/test_m28_kontoblatt.py::test_filter_untermenue` (4 Varianten) | D-292: Untermenü „Filter“ hat zwei Einträge für den Betrag | erwartete Liste der Einträge ergänzt |
| eigene `test_browser_tastatur.py` (2 Tests) | D-292: `v d` entfällt, `f w` ist „diese Woche“, Hilfe auf `h`, F6 mit „Aktionen“ | Panel über den Knopf eingeklappt, Erwartungen nachgezogen |
| `m28/test_m28_kontoblatt.py::test_kuerzel_aktionen_und_vortasten` | Prüfte den Fokus ohne zu warten; schlug in 4 von 6 Läufen fehl (auch in legacy-tests) | wartet auf den Fokus |
| `m8/test_m8_auslieferung.py::test_manifest` | D-286: Im Mock-Modus heißt die Anwendung im Manifest „Kontor Test“ (eigene Symbole unter denselben Adressen) | erwartet `name` und `short_name` „Kontor Test“; die übrigen Prüfungen (Größen, `maskable`, Farben) unverändert |
| `m30/test_m30_oberflaeche.py::test_regelliste` | Tastendruck auf einen Griff, den die Seite gerade neu aufbaut; schlug gelegentlich fehl | drückt erneut, solange die Reihenfolge unverändert ist |
| `m15/test_m15_oberflaeche.py::test_details_vorschlag_und_kandidaten`, `m8/test_m8_kontextmenue.py::test_kategorie_setzen_umbuchung_meldet_ablehnung`, `m8/test_m8_kontoansicht.py::test_liste_gleich_rest_und_darstellung` (2) | schlagen fehl (die letzten drei wegen D-242, der erste nicht untersucht) | nicht angepasst; stehen in `abgewaehlt.txt` und schlagen mit `--alle` weiter fehl |
| eigene `test_browser_ausdruck.py::test_tags_im_kontoblatt_bearbeiten` | schlug einmal in vier Läufen fehl, danach nicht mehr | unverändert; beobachten |
| eigene `test_browser_spalten.py::test_markierung_der_zeilen`, `m22/test_m22_oberflaeche.py::test_markierung_rangfolge_und_darstellung` (abgewählt) | D-254: Zeilenfarbe folgt nur dem Status, `kategorisiert` entfällt | erwartet `vorlaeufig`/`bestaetigt`; Unterscheidbarkeit an importiert, vorläufig, bestätigt; „folgt Änderungen“ über Statuswechsel statt Kategorie |
| `test_buchungen.py`, `test_invarianten.py` (Tabelle `UEBERGAENGE`), `m28/test_m28_kontoblatt.py::test_bestaetigen_vorlaeufig_bleibt_und_zuruecknehmen` (abgewählt) | D-257: `vorlaeufig → bestaetigt` ist zulässig; Bestätigen erfasst auch vorläufige Buchungen | Übergang in die Tabelle aufgenommen; erwartet nach dem Bestätigen `bestaetigt` (nicht ausgeführt, nur nach Lektüre angepasst) |
| eigene `test_browser_sammel3.py` (2 Tests), `m28/test_m28_kontoblatt.py`, `m28/test_m28_seiten.py`, `m32/test_m32_oberflaeche.py` | D-262: Das Bestätigungs-Tag heißt „<Name>-Bestätigt“ statt „B-<Name>“ | erwarteter Tag-Name ersetzt (nicht ausgeführt, nur nach Lektüre angepasst) |
| `m2/test_m2_vorschlag.py` (3 Tests), `m3/test_m3_abstimmung.py::test_sperre_abgestimmter_buchungen`, `m4/test_m4_vorlagen_sync.py` (2 Tests) | D-261: Vorschlag und Split-Vorlage machen `vorlaeufig`, Annehmen `bestaetigt`, Ablehnen wieder `importiert` | erwarteter Status angepasst |
| `test_buchungen.py::test_kategorie_setzen`, `test_mehrfach.py::test_kategorie_genau_die_markierten`, `m12/test_m12_rest.py::test_abgeglichen_verlassen_braucht_entsperren` | D-261: Zuordnung von Hand (Kategorie, Splits) macht `bestaetigt` | erwarteter Status angepasst |
| `m30/test_m30_ausdruck.py::test_sprache_felder` (Hilfe `m30.FELDER`), `spec/test_openapi.py::test_m5_schemas` | D-263: Filterfeld `verdächtig`; D-271: `position_id` gehört nur zur Buchungsliste, nicht zum Export | Feld bzw. Ausnahme ergänzt |
| `m30/test_m30_ausdruck.py::test_sprache_felder` (Hilfe `m30.FELDER`) | D-297: Filterfeld `unbestätigt` | Feld ergänzt |
| eigene `test_browser.py::test_panels_und_layout` | D-265, D-266: kein Panel Kategorien; Einzelheiten rechts oder unten | prüft Breite und Andocken der Einzelheiten |
| `m28/test_m28_kontoblatt.py::test_filter_untermenue`, `m8/test_m8_panels_mobil.py::test_groesse_per_tastatur`, `::test_mobil_kein_andocken_layout_bleibt` | D-271: Filterwechsel behält die Auswahl; D-265: kein Panel Kategorien | Auswahl = gewählte Buchung; Griff und Andocken der Einzelheiten statt des Panels Kategorien |
| eigene `test_browser_ausdruck.py::test_tags_im_kontoblatt_bearbeiten` | öffnete den Tag-Dialog, bevor die Liste neu geladen war; erneut rot im CI-Lauf vom 2026-11-24 | wartet, bis die Zeile das neue Tag zeigt (D-274) |
| `m8/test_m8_split_dnd.py::test_split_bearbeiten` | D-272: Splits speichern setzt bei gewählter Person auch deren Tag (weitere Änderungen im Protokoll) | zählt nur die Änderung der Splits; die Tag-Änderungen sind zugelassen |
| `m26/test_m26_oberflaeche.py::test_erfassen_schwebend_und_titelzeile` | D-283: `buchung-erfassen` ist mobil ausgeblendet | prüft, dass der Knopf vorhanden, aber nicht sichtbar ist |
| eigene `test_browser.py::test_bericht_sprung_mobil_mit_nachladen_nicht_verdeckt`; `m26/test_m26_oberflaeche.py::test_suchtreffer_kompakt_und_tippen_springt` | D-281: mobil wählt der Sprung zu einer Buchung nichts mehr aus | Ziel ist markiert (`data-markiert`) und fokussiert, Auswahl leer |
| eigene `test_browser.py::test_mobil`; `m26/test_m26_oberflaeche.py::test_zurueck_beendet_auswahl_ohne_ansicht_zu_verlassen`, `::test_kontextmenue_als_blatt`; `m8/test_m8_panels_mobil.py::test_wischen_links_setzt_kategorie_und_rueckgaengig`; `m18/test_m18_oberflaeche.py::test_mobil_marke_und_kamera` | D-278: mobil markiert Tippen nur, Doppeltipp öffnet die Einzelheiten, lange Berührung öffnet das Kontextmenü, Wischen nach rechts bestätigt | Auswahlmodus über `km-auswahl` (Hilfen `m8.auswahl_starten_mobil`, `m8.doppeltipp`), weitere Zeilen durch Tippen |
| `m26/test_m26_oberflaeche.py::test_kopfzeile_eine_zeile_reihenfolge_und_groesse` | D-279: „Wiederholen“ fehlt unter 403 px, die Kopfzeile ist wieder einzeilig | `m26.KOPF` ohne `wiederholen-knopf`; „eine Zeile“ wird wieder geprüft |
| eigene `test_mail_fortschritt_eigen.py::test_hintergrund_mit_fortschritt`, `test_oberflaeche.py::test_oberflaeche_nutzt_nur_spezifizierte_api` | D-284: `GET /api/mail/abruf/stand` nennt zusätzlich `automatisch` und `intervall_minuten`; neuer Pfad `GET /api/bestand/stand` | erwarteter Stand um die zwei Felder ergänzt; Pfad in `REST` aufgenommen |
| abgewählte Tests zu 36.3.1/36.3.2/36.4.1 (`m26`: lange Berührung wählt aus, Wischen rechts wählt; `m8/test_m8_panels_mobil.py`: Wischen rechts) | D-278 löst diese Festlegungen ab | nicht angepasst (abgewählt); vor einem Wiederaufnehmen in `abgewaehlt.txt` nach `oberflaeche.md` 43 umschreiben |
| `spec/test_openapi.py::test_alle_operationen_vorhanden`, eigene `test_oberflaeche.py::test_oberflaeche_nutzt_nur_spezifizierte_api` | D-280: drei neue Operationen unter `/api/saldoausgleich/paare` | erwartete Operationen bzw. Pfade ergänzt |
| `spec/test_openapi.py::test_alle_operationen_vorhanden` | D-295: neue Operation `POST /api/regeln/{regel_id}/uebernehmen` | in `OPERATIONEN_M30` ergänzt |
| eigene `test_oberflaeche.py::test_oberflaeche_nutzt_nur_spezifizierte_api` | D-303: neuer Pfad `/api/export/nachweis` (Nachweis als PDF) | Pfad ergänzt |

Stabilität: Nach den Änderungen lief der Browser-Teil der Gesamtsuite viermal hintereinander grün.
| eigene `test_m6_eigen.py::test_sicherung_der_schemaversion_2_einspielbar_und_postfach_bleibt_erhalten`, `test_geplant_eigen.py::test_sicherung_und_altbestand` | D-302: Sicherungsdatei Schemaversion 11 (Einstellungen) | erwartete Schemaversion 11 bzw. mindestens 10 |
| eigene `test_browser_einstellungen.py::test_suche_und_erweitert` | D-302: neuer Eintrag „Sicherungspunkte“ im Bereich Daten (Synonym „backup“) | drei statt zwei Treffer für „backup“ |
| `m31/test_m31_lernmodell.py::test_einstellungen_nicht_in_der_sicherung`, `m25/test_m25_rest.py::test_sicherung_rundreise` | D-302: Einstellungen der Instanz (Lernschwelle, automatische Regeln, Vorgabe des Betragsfilters) gehören ab Schemaversion 11 zur Sicherung und kommen beim Einspielen mit; die Inhaltsprüfsumme bleibt ohne sie | erwarten die Einstellungen der Quelle statt der des Ziels |
| `spec/test_openapi.py::test_alle_operationen_vorhanden` | D-302: sieben neue Operationen unter `/api/sicherung/punkte` | in `OPERATIONEN_M9` ergänzt |
| `m7/test_m7_betrieb.py::test_sicherung_service_und_timer` | D-302: Die zeitgesteuerte Sicherung legt stündlich Sicherungspunkte an (`sicherungspunkte.md` 8) | `ExecStart` mit `stunde --verzeichnis /var/lib/kontor/sicherungen`, `OnCalendar=hourly` |
| `app/m8/test_m8_kontoansicht.py::test_vorschlaege_annehmen_und_ablehnen` | D-305: Knöpfe ✓/✗ in der Zeile entfallen | Desktop über das Kontextmenü (`km-vorschlag-annehmen`/`-ablehnen`); Handy: Annehmen durch Wischen nach rechts, Ablehnen über die Schnittstelle (der Weg über Kontextmenü/Einzelheiten ist anderswo geprüft); Prüfung „Klick ändert die Auswahl nicht“ entfällt mit den Knöpfen |
| `app/m15/test_m15_oberflaeche.py` (Vorschlagsmarken) | D-305 | statt „Knöpfe mobil sichtbar“ nun „keine Knöpfe“ (Desktop und Handy) |
| eigene `test_browser_vorschlag_sofort.py` | D-305 | Entscheidung über Zeile markieren und `a`/`A` statt Knopf |
